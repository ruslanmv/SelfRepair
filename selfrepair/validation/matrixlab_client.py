"""MatrixLab sandbox HTTP client.

SelfRepair asks MatrixLab to validate a repair in a sandbox. This client never
writes code; it submits a run/validate request and parses the response.

Contract (MatrixLab implements the server side):
    base url : {MATRIXLAB_URL}  (default http://localhost:8765)
    POST /repo/run, /repo/validate-patch with
        {client_id, workspace_id, repo_url, branch, profile,
         commands?, timeout_seconds?, artifacts?}
    response {run_id, status, exit_code, stdout, stderr, duration_ms,
              artifacts:[{name,url}]}
    GET /health

Degrades gracefully: ``health()`` returns False when unreachable, and run /
validate calls return a stub result so dry-run flows complete offline.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DEFAULT_MATRIXLAB_URL = "http://localhost:8765"


class RunResult(BaseModel):
    run_id: str = ""
    status: str = "unknown"
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    artifacts: list[dict[str, str]] = Field(default_factory=list)
    stubbed: bool = False

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> RunResult:
        return cls(
            run_id=payload.get("run_id", ""),
            status=payload.get("status", "unknown"),
            exit_code=payload.get("exit_code"),
            stdout=payload.get("stdout", ""),
            stderr=payload.get("stderr", ""),
            duration_ms=int(payload.get("duration_ms", 0) or 0),
            artifacts=list(payload.get("artifacts", []) or []),
            stubbed=bool(payload.get("stubbed", False)),
        )

    @property
    def passed(self) -> bool:
        return self.status in ("passed", "success", "ok") or self.exit_code == 0


class MatrixLabClient:
    def __init__(
        self,
        base_url: str = DEFAULT_MATRIXLAB_URL,
        *,
        token: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = (base_url or DEFAULT_MATRIXLAB_URL).rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def health(self) -> bool:
        """Return True if MatrixLab is reachable and healthy, else False."""
        try:
            resp = httpx.get(f"{self.base_url}/health", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def _build_request(
        self,
        *,
        client_id: str,
        workspace_id: str,
        repo_url: str,
        branch: str,
        profile: str,
        commands: list[str] | None = None,
        timeout_seconds: int | None = None,
        artifacts: list[str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "client_id": client_id,
            "workspace_id": workspace_id,
            "repo_url": repo_url,
            "branch": branch,
            "profile": profile,
        }
        if commands is not None:
            body["commands"] = commands
        if timeout_seconds is not None:
            body["timeout_seconds"] = timeout_seconds
        if artifacts is not None:
            body["artifacts"] = artifacts
        return body

    def _post(self, endpoint: str, body: dict[str, Any]) -> RunResult:
        try:
            resp = httpx.post(
                f"{self.base_url}{endpoint}",
                json=body,
                headers=self._headers(),
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return RunResult.from_payload(resp.json())
        except Exception as exc:
            logger.warning("MatrixLab unreachable (%s), returning stub: %s", endpoint, exc)
            return RunResult(
                run_id="",
                status="skipped",
                exit_code=None,
                stdout="",
                stderr="matrixlab unreachable",
                duration_ms=0,
                artifacts=[],
                stubbed=True,
            )

    def run(self, **kwargs: Any) -> RunResult:
        """POST /repo/run."""
        return self._post("/repo/run", self._build_request(**kwargs))

    def validate_patch(self, **kwargs: Any) -> RunResult:
        """POST /repo/validate-patch."""
        return self._post("/repo/validate-patch", self._build_request(**kwargs))
