"""GitPilot coder HTTP client.

SelfRepair DIAGNOSES and PLANS; GitPilot WRITES code. This client sends the
repair-plan (the JSON produced by ``selfrepair.planning.repair_plan``) to a
GitPilot server and returns the repair-response. It NEVER writes code itself.

Contract (GitPilot implements the server side):
    base url : {GITPILOT_URL}  (default http://localhost:9000)
    request  : the repair-plan JSON
    response : {patch_preview, changed_files, review, sandbox_result,
                risk_level, status}

When GitPilot is unreachable the client degrades to a deterministic STUB
repair-response so the dry-run flow completes offline.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DEFAULT_GITPILOT_URL = "http://localhost:9000"


def _normalize_changed_files(value: Any) -> list[str]:
    """Normalize ``changed_files`` to a consistent list of path strings.

    GitPilot returns a list of objects ``{path, change_type}``; the offline
    stub returns a list of plain path strings. Accept both (and ignore
    malformed entries) so callers always get ``list[str]`` of paths.
    """
    out: list[str] = []
    for item in value or []:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            path = item.get("path")
            if isinstance(path, str) and path:
                out.append(path)
        # anything else is silently skipped (defensive / forward-compatible)
    return out


def _changed_files_detail(value: Any) -> list[dict[str, Any]]:
    """Preserve the full ``{path, change_type}`` detail when available.

    String entries are promoted to ``{"path": <str>, "change_type": "modified"}``
    so the detailed view is uniform across GitPilot and stub responses.
    """
    out: list[dict[str, Any]] = []
    for item in value or []:
        if isinstance(item, str):
            out.append({"path": item, "change_type": "modified"})
        elif isinstance(item, dict):
            path = item.get("path")
            if isinstance(path, str) and path:
                out.append(
                    {
                        "path": path,
                        "change_type": item.get("change_type", "modified"),
                    }
                )
    return out


class RepairResponse(BaseModel):
    """Parsed GitPilot repair-response.

    Tolerant of both GitPilot's real response shape and the offline stub:

    * ``review`` may be a STRING (GitPilot) or a dict (stub) — both accepted.
    * ``changed_files`` may be a list of objects ``{path, change_type}``
      (GitPilot) or a list of strings (stub) — normalized to ``list[str]`` of
      paths, with the full detail kept in ``changed_files_detailed``.
    * ``status`` may be any of ok|blocked|error|needs_approval (GitPilot) or
      the stub values (dry_run|planned|unknown) — never crashes.
    """

    status: str = "unknown"
    risk_level: str = "low"
    patch_preview: str = ""
    changed_files: list[str] = Field(default_factory=list)
    changed_files_detailed: list[dict[str, Any]] = Field(default_factory=list)
    # ``review`` may be a string (GitPilot) or a dict (stub); accept both.
    review: Any = Field(default_factory=dict)
    sandbox_result: dict[str, Any] = Field(default_factory=dict)
    stubbed: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> RepairResponse:
        raw_changed = payload.get("changed_files", []) or []
        review = payload.get("review", {})
        if review is None:
            review = {}
        sandbox = payload.get("sandbox_result")
        if not isinstance(sandbox, dict):
            sandbox = {}
        return cls(
            status=payload.get("status", "unknown"),
            risk_level=payload.get("risk_level", "low"),
            patch_preview=payload.get("patch_preview", ""),
            changed_files=_normalize_changed_files(raw_changed),
            changed_files_detailed=_changed_files_detail(raw_changed),
            review=review,
            sandbox_result=sandbox,
            stubbed=bool(payload.get("stubbed", False)),
            raw=payload,
        )


class GitPilotClient:
    def __init__(
        self,
        base_url: str = DEFAULT_GITPILOT_URL,
        *,
        token: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = (base_url or DEFAULT_GITPILOT_URL).rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def available(self) -> bool:
        try:
            resp = httpx.get(f"{self.base_url}/health", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def repair(self, plan: dict[str, Any], *, dry_run: bool = True) -> RepairResponse:
        """Send a repair-plan to GitPilot and return the repair-response.

        In dry-run no PR is created (the plan carries ``mode: dry_run``). On any
        connection error we degrade to a stub response so offline flows work.
        """
        payload = dict(plan)
        if dry_run:
            payload.setdefault("mode", "dry_run")
        try:
            resp = httpx.post(
                f"{self.base_url}/repair",
                json=payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return RepairResponse.from_payload(resp.json())
        except Exception as exc:
            logger.warning("GitPilot unreachable, using stub repair-response: %s", exc)
            return self.stub_response(plan, dry_run=dry_run)

    @staticmethod
    def stub_response(plan: dict[str, Any], *, dry_run: bool = True) -> RepairResponse:
        """Deterministic offline stub mirroring the GitPilot contract shape."""
        allowed = list(plan.get("allowed_paths", []) or [])
        issues = plan.get("issues", []) or []
        risk = plan.get("risk_level") or "low"
        preview_lines = [f"# stub patch preview ({len(issues)} issue(s))"]
        for path in allowed:
            preview_lines.append(f"--- a/{path}\n+++ b/{path}")
        return RepairResponse(
            status="dry_run" if dry_run else "planned",
            risk_level=risk,
            patch_preview="\n".join(preview_lines),
            changed_files=allowed,
            review={"summary": "stubbed review (GitPilot offline)", "approved": False},
            sandbox_result={"status": "skipped", "reason": "stub"},
            stubbed=True,
            raw={"stub": True, "plan_task_id": plan.get("task_id")},
        )
