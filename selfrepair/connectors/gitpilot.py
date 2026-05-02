"""GitPilot HTTP/SSE connector.

Replaces the subprocess shell-out in `selfrepair/gitpilot/client.py`. GitPilot
runs as a sidecar service; SelfRepair posts repair requests and streams events
back. GitPilot never sees git credentials — it operates on a git bundle and
returns a patch.

Contract: `docs/architecture/system-design.md` §5.1.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import httpx

logger = logging.getLogger(__name__)

PermissionMode = Literal["plan", "ask", "auto"]


class GitPilotError(RuntimeError):
    """Raised on HTTP error or non-success terminal event."""


@dataclass(frozen=True)
class Workspace:
    """Read-only handle to the source GitPilot operates on.

    Always a git bundle URL — GitPilot never receives a remote credential.
    """

    kind: Literal["git_bundle"]
    url: str
    checkout: str = "main"


@dataclass(frozen=True)
class Budget:
    """Hard caps GitPilot must honor; abort + report partial when exceeded."""

    tokens: int = 200_000
    wall_seconds: int = 600
    usd: float = 0.50


@dataclass(frozen=True)
class RepairRequest:
    repair_id: str
    workspace: Workspace
    context: dict[str, Any]
    permission_mode: PermissionMode = "plan"
    tools_allowed: tuple[str, ...] = ("read_file", "edit_file", "run_tests")
    tools_denied: tuple[str, ...] = ("network", "git_push")
    budget: Budget = field(default_factory=Budget)
    model_routing: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RepairResult:
    repair_id: str
    success: bool
    patch_url: str | None
    provenance: dict[str, Any]
    events: tuple[dict[str, Any], ...]
    error: str | None = None


class GitPilotClient:
    """HTTP client for the GitPilot agent service.

    Usage:
        with GitPilotClient(base_url, token) as client:
            result = client.repair(request)

    For long-running repairs prefer `stream()` so the worker can heartbeat as
    events arrive.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._client = client or httpx.Client(timeout=timeout)

    def repair(self, request: RepairRequest) -> RepairResult:
        """Submit a repair and block until terminal event."""
        events = list(self.stream(request))
        return self._materialize(request.repair_id, events)

    def stream(self, request: RepairRequest) -> Iterator[dict[str, Any]]:
        """Submit a repair and yield SSE events as they arrive."""
        payload = self._serialize(request)
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Idempotency-Key": request.repair_id,
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        }
        url = f"{self._base_url}/v1/agents/repair"
        with self._client.stream(
            "POST", url, json=payload, headers=headers, timeout=None
        ) as resp:
            if resp.status_code >= 400:
                body = resp.read().decode("utf-8", errors="replace")
                raise GitPilotError(f"gitpilot {resp.status_code}: {body}")
            for event in _iter_sse(resp.iter_lines()):
                yield event
                if event.get("event") in ("done", "error"):
                    return

    @staticmethod
    def _serialize(request: RepairRequest) -> dict[str, Any]:
        return asdict(request)

    @staticmethod
    def _materialize(
        repair_id: str, events: list[dict[str, Any]]
    ) -> RepairResult:
        if not events:
            return RepairResult(
                repair_id=repair_id,
                success=False,
                patch_url=None,
                provenance={},
                events=(),
                error="no events received from gitpilot",
            )
        terminal = events[-1]
        if terminal.get("event") == "done":
            data = terminal.get("data") or {}
            return RepairResult(
                repair_id=repair_id,
                success=True,
                patch_url=data.get("patch_url"),
                provenance=data.get("signed_provenance") or {},
                events=tuple(events),
            )
        err_data = terminal.get("data") or {}
        return RepairResult(
            repair_id=repair_id,
            success=False,
            patch_url=None,
            provenance={},
            events=tuple(events),
            error=str(err_data.get("error", "unknown")),
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> GitPilotClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def _iter_sse(lines: Iterator[str]) -> Iterator[dict[str, Any]]:
    """Minimal SSE parser. Each event is `event:` line + `data:` line(s) + blank.

    Multi-line data is concatenated with newlines per the SSE spec.
    Lines starting with `:` are comments / heartbeats and ignored.
    """
    event_name: str | None = None
    data_buf: list[str] = []
    for raw in lines:
        if raw is None:
            continue
        line = raw.rstrip("\r")
        if line == "":
            if event_name is not None:
                payload_text = "\n".join(data_buf)
                try:
                    payload = json.loads(payload_text) if payload_text else {}
                except json.JSONDecodeError:
                    payload = {"raw": payload_text}
                yield {"event": event_name, "data": payload}
            event_name = None
            data_buf = []
            continue
        if line.startswith(":"):
            continue  # comment / heartbeat
        field_name, _, value = line.partition(":")
        value = value.lstrip(" ")
        if field_name == "event":
            event_name = value
        elif field_name == "data":
            data_buf.append(value)
