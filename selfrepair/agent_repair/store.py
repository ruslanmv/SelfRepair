"""Persistence for agent repairs: the row, its state machine, its events, and audit rows for operator actions.

The state only moves through TRANSITIONS. A move that is not listed raises InvalidRepairTransition, so a late
result from a cancelled job can never overwrite the cancellation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.agent_repair.models import AgentRepair, AgentRepairEvent
from selfrepair.persistence.repositories.audit import AuditRepository

TRANSITIONS: dict[str, set[str]] = {
    "planning": {"plan_ready", "failed", "cancelled"},
    "plan_ready": {"implementing", "cancelled"},
    "implementing": {"patch_ready", "failed", "cancelled"},
    "patch_ready": {"implementing", "pr_draft", "cancelled"},   # implementing again = an approved retry
    "failed": {"implementing"},                                 # an approved retry after a failed implementation
    "pr_draft": set(),
    "cancelled": set(),
}
ACTIVE = {"planning", "implementing"}


class InvalidRepairTransition(Exception):
    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"an agent repair cannot go from {current} to {target}")
        self.current, self.target = current, target


class AgentRepairStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditRepository(session)

    async def get(self, org_id: uuid.UUID, repair_id: uuid.UUID) -> AgentRepair | None:
        row = await self._session.get(AgentRepair, repair_id)
        return row if row is not None and row.org_id == org_id else None

    async def get_any(self, repair_id: uuid.UUID) -> AgentRepair | None:
        """For the worker, which acts on a job the API already scoped to its org."""
        return await self._session.get(AgentRepair, repair_id)

    async def by_attempt(self, org_id: uuid.UUID, attempt_id: str) -> AgentRepair | None:
        stmt = select(AgentRepair).where(AgentRepair.org_id == org_id, AgentRepair.attempt_id == attempt_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def create(self, **fields: Any) -> AgentRepair:
        row = AgentRepair(**fields, state="planning")
        self._session.add(row)
        await self._session.flush()
        await self.event(row, "intake", "accepted for a read-only plan", {"evidence_id": row.evidence_id, "base_commit": row.base_commit})
        return row

    async def event(self, row: AgentRepair, stage: str, message: str, payload: dict[str, Any] | None = None,
                    level: str = "info") -> AgentRepairEvent:
        seq = (await self._session.execute(
            select(func.coalesce(func.max(AgentRepairEvent.seq), 0)).where(AgentRepairEvent.repair_id == row.id))).scalar_one() + 1
        ev = AgentRepairEvent(repair_id=row.id, seq=seq, stage=stage, level=level, message=message[:4000], payload=payload)
        self._session.add(ev)
        await self._session.flush()
        return ev

    async def events(self, row: AgentRepair, after: int = 0, limit: int = 200) -> list[AgentRepairEvent]:
        stmt = (select(AgentRepairEvent).where(AgentRepairEvent.repair_id == row.id, AgentRepairEvent.seq > after)
                .order_by(AgentRepairEvent.seq).limit(limit))
        return list((await self._session.execute(stmt)).scalars())

    async def move(self, row: AgentRepair, to: str, message: str, *, level: str = "info", payload: dict[str, Any] | None = None,
                   **fields: Any) -> AgentRepair:
        if to not in TRANSITIONS.get(row.state, set()):      # no self-moves: a second cancel is refused, not ignored
            raise InvalidRepairTransition(row.state, to)
        previous = row.state
        for key, value in fields.items():
            setattr(row, key, value)
        row.state = to
        row.updated_at = datetime.now(UTC)
        await self.event(row, to, message, {"from": previous, "to": to, **(payload or {})}, level=level)
        return row

    async def audit(self, row: AgentRepair, actor: str, action: str, payload: dict[str, Any] | None = None, ip: str | None = None) -> None:
        await self._audit.record(org_id=row.org_id, actor=actor[:255], action=action, target_type="agent_repair",
                                 target_id=str(row.id), ip=ip, payload=payload)


def as_dict(row: AgentRepair) -> dict[str, Any]:
    """The contract's view of a job (docs/agent-repair.md)."""
    return {
        "job_id": str(row.id), "state": row.state, "attempt_id": row.attempt_id, "case_id": row.case_id,
        "evidence_id": row.evidence_id, "repository": {"url": row.repo_url, "base_commit": row.base_commit, "ref": row.ref},
        "coder": row.coder, "gitpilot_run_id": row.gitpilot_task_id, "plan": row.plan, "scope": row.scope,
        "patch": row.patch if row.state in ("patch_ready", "pr_draft") else None, "patch_sha256": row.patch_sha256,
        "changed_files": row.changed_files, "branch": row.branch, "static_checks": row.static_checks,
        "pr": {"url": row.pr_url, "number": row.pr_number, "draft": True} if row.pr_url else None,
        "retries": row.retries, "error": row.error, "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
