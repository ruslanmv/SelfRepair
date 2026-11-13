"""The worker side of an agent repair: one function per step, each run once per enqueue.

    plan       GitPilot's health (demo mode refused), then its read-only planner -> plan_ready
    implement  GitPilot /repair (dry_run, allowed_paths = approved scope) -> scope check -> a workspace at the pinned
               base commit -> git apply -> static checks -> patch_ready

Cancellation is cooperative and safe: every step re-reads the row before it writes, and a step that finds the job
cancelled records nothing but an event. Every failure is written to the row and its events with the reason; none
is swallowed. The draft pull request is not a worker step: it runs in the request that asks for it
(selfrepair/api/routes/agent_repairs.py). Each GitPilot call writes an audit row before it is made.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from selfrepair.agent_repair import gitpilot as gp, settings as cfg, workspace as ws
from selfrepair.agent_repair.models import AgentRepair
from selfrepair.agent_repair.store import AgentRepairStore, InvalidRepairTransition

logger = logging.getLogger(__name__)


@dataclass
class Deps:
    """What a step calls outside SelfRepair. Tests replace these; production uses the defaults."""

    endpoint: Callable[[str], gp.Endpoint] = gp.endpoint
    health: Callable[[gp.Endpoint], dict[str, Any]] = gp.health
    plan: Callable[..., dict[str, Any]] = gp.plan
    repair: Callable[[gp.Endpoint, dict[str, Any]], Any] = gp.repair
    settings: Callable[[], cfg.AgentRepairSettings] = cfg.load
    extra: dict[str, Any] = field(default_factory=dict)


async def run_step(sessionmaker: async_sessionmaker[AsyncSession], repair_id: uuid.UUID, step: str, deps: Deps | None = None) -> str:
    deps = deps or Deps()
    if step == "plan":
        return await _plan(sessionmaker, repair_id, deps)
    if step == "implement":
        return await _implement(sessionmaker, repair_id, deps)
    raise ValueError(f"unknown agent-repair step {step}")


async def _load(sessionmaker: async_sessionmaker[AsyncSession], repair_id: uuid.UUID) -> dict[str, Any] | None:
    async with sessionmaker() as session:
        row = await AgentRepairStore(session).get_any(repair_id)
        if row is None:
            return None
        return {c.name: getattr(row, c.name) for c in AgentRepair.__table__.columns}


async def _finish(sessionmaker: async_sessionmaker[AsyncSession], repair_id: uuid.UUID, expected: str, to: str, message: str,
                  *, level: str = "info", payload: dict[str, Any] | None = None, **fields: Any) -> str:
    """Write a step's result, unless the job moved meanwhile (cancelled): then only an event says so."""
    async with sessionmaker() as session:
        store = AgentRepairStore(session)
        row = await store.get_any(repair_id)
        if row is None:
            return "missing"
        if row.state != expected:
            await store.event(row, "discarded", f"a {expected} result arrived after the job became {row.state}; it was not applied", level="warning")
            await session.commit()
            return row.state
        try:
            await store.move(row, to, message, level=level, payload=payload, **fields)
        except InvalidRepairTransition as exc:
            await store.event(row, "error", str(exc), level="error")
        await session.commit()
        return row.state


async def _note(sessionmaker: async_sessionmaker[AsyncSession], repair_id: uuid.UUID, stage: str, message: str,
                payload: dict[str, Any] | None = None, *, audit: str | None = None) -> None:
    """An event on the job; with `audit`, also an audit row (each GitPilot call gets one, before it is made)."""
    async with sessionmaker() as session:
        store = AgentRepairStore(session)
        row = await store.get_any(repair_id)
        if row is not None:
            await store.event(row, stage, message, payload)
            if audit:
                await store.audit(row, "selfrepair-worker", audit, payload)
            await session.commit()


async def _coder(deps: Deps, row: dict[str, Any]) -> tuple[gp.Endpoint, dict[str, Any]]:
    settings = deps.settings()
    ep = deps.endpoint(str(row["org_id"]))
    info = await asyncio.to_thread(deps.health, ep)
    demo = bool(info.get("coder_demo"))
    coder = {"agent": "gitpilot", "version": info.get("version"), "provider": settings.coder_provider,
             "model": settings.coder_model, "demo": demo}
    if demo and not settings.allow_demo_coder:
        raise gp.CoderError("GitPilot's coder runs in demo mode (GITPILOT_CODER_DEMO): its output would be a stub. "
                            "Set GITPILOT_CODER_DEMO=false on GitPilot.")
    return ep, coder


async def _plan(sessionmaker: async_sessionmaker[AsyncSession], repair_id: uuid.UUID, deps: Deps) -> str:
    row = await _load(sessionmaker, repair_id)
    if row is None or row["state"] != "planning":
        return "skipped"
    try:
        ep, coder = await _coder(deps, row)
        await _note(sessionmaker, repair_id, "plan", "GitPilot read-only planner started",
                    {"coder": coder, "base_commit": row["base_commit"]}, audit="agent_repair.gitpilot_plan")
        result = await asyncio.to_thread(deps.plan, ep, repo_url=row["repo_url"], ref=row["ref"], evidence=row["evidence"])
        plan = gp.plan_from_result(result)
        if not plan["files"]:
            raise gp.CoderError("GitPilot's plan names no file to create, modify or delete")
    except gp.CoderError as exc:
        return await _finish(sessionmaker, repair_id, "planning", "failed", str(exc), level="error", error=str(exc))
    except Exception as exc:  # an unexpected error still ends the step visibly, never as a job stuck in planning
        logger.exception("agent repair %s: planning crashed", repair_id)
        message = f"internal error while planning: {type(exc).__name__}: {exc}"
        return await _finish(sessionmaker, repair_id, "planning", "failed", message, level="error", error=message)
    return await _finish(sessionmaker, repair_id, "planning", "plan_ready", f"plan ready: {len(plan['files'])} file(s)",
                         payload={"files": plan["files"]}, plan=plan, coder=coder, error=None)


def _repair_body(row: dict[str, Any], settings: cfg.AgentRepairSettings) -> dict[str, Any]:
    case = (row["evidence"].get("case") or {})
    plan = row["plan"] or {}
    return {
        "client_id": "selfrepair", "workspace_id": str(row["org_id"]),
        "task_id": f"lr-{row['attempt_id']}-{row['retries']}"[:128], "repo_url": row["repo_url"], "branch": row["ref"] or "main",
        "mode": "dry_run",            # a patch only: SelfRepair pushes and opens the draft PR itself, after LangReplay verified
        "issues": [{"id": str(case.get("id") or row["case_id"])[:64], "severity": "high",
                    "description": gp.goal_from_evidence(row["evidence"], read_only=False)[:2000],
                    "recommended_action": str(plan.get("summary") or "")[:2000]}],
        "allowed_paths": list(row["scope"] or []), "forbidden_paths": list(ws.FORBIDDEN),
        "coder": {"provider": settings.coder_provider, "model": settings.coder_model},
        "sandbox": {"provider": "matrixlab", "profile": "default", "required": False},
        "human_approval": True,
        "auto_merge": False,
    }


async def _implement(sessionmaker: async_sessionmaker[AsyncSession], repair_id: uuid.UUID, deps: Deps) -> str:
    row = await _load(sessionmaker, repair_id)
    if row is None or row["state"] != "implementing":
        return "skipped"
    settings = deps.settings()
    folder = ws.root() / f"{repair_id}-{row['retries']}"
    try:
        ep, coder = await _coder(deps, row)
        body = _repair_body(row, settings)
        await _note(sessionmaker, repair_id, "repair", f"GitPilot /repair started within {', '.join(body['allowed_paths'])}",
                    {"task_id": body["task_id"], "coder": coder, "allowed_paths": body["allowed_paths"]},
                    audit="agent_repair.gitpilot_repair")
        resp = await asyncio.to_thread(deps.repair, ep, body)
        if getattr(resp, "stubbed", False):
            raise gp.CoderError("GitPilot could not be reached: SelfRepair's client returned its offline stub, which is not a repair")
        if resp.status != "ok":
            detail = "; ".join(str(x) for x in (resp.raw.get("warnings") or []) + (resp.raw.get("messages") or []))[:500]
            raise gp.CoderError(f"GitPilot answered {resp.status}" + (f": {detail}" if detail else ""))
        patch = resp.patch_preview or ""
        if not patch.strip():
            raise gp.CoderError("GitPilot returned no patch")
        paths = list(dict.fromkeys(ws.patch_paths(patch) + list(resp.changed_files)))
        ws.check_paths(paths, list(row["scope"] or []))
        await _note(sessionmaker, repair_id, "repair", f"patch received for {', '.join(paths)}", {"risk_level": resp.risk_level})
        await asyncio.to_thread(ws.clone_at, row["repo_url"], row["base_commit"], folder)
        await asyncio.to_thread(ws.apply_patch, folder, patch)
        await _note(sessionmaker, repair_id, "validate", f"patch applies to {row['base_commit'][:12]}; running static checks")
        checks = await asyncio.to_thread(ws.run_checks, folder, settings.checks, settings.check_timeout_s)
    except (gp.CoderError, ws.WorkspaceError) as exc:
        return await _finish(sessionmaker, repair_id, "implementing", "failed", str(exc), level="error", error=str(exc))
    except Exception as exc:  # see _plan
        logger.exception("agent repair %s: implementation crashed", repair_id)
        message = f"internal error while implementing: {type(exc).__name__}: {exc}"
        return await _finish(sessionmaker, repair_id, "implementing", "failed", message, level="error", error=message)
    finally:
        await asyncio.to_thread(ws.remove, folder)
    sha = "sha256:" + hashlib.sha256(patch.encode("utf-8")).hexdigest()
    return await _finish(sessionmaker, repair_id, "implementing", "patch_ready",
                         f"patch ready; static checks {checks['status']}", payload={"static_checks": checks["status"]},
                         patch=patch, patch_sha256=sha, changed_files=paths, static_checks=checks,
                         branch=f"langreplay/{row['attempt_id']}", coder=coder, gitpilot_task_id=body["task_id"], error=None)
