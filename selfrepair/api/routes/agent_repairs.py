"""`/v1/agent-repairs`: the API LangReplay calls (package: selfrepair/agent_repair) (contract: docs/agent-repair.md).

Every route depends on `service_caller` (bearer token + HMAC signature, org fixed by configuration). Bodies are
parsed from the exact bytes that were signed. Each operator action writes an audit row in the same transaction as
the state change; the worker writes events. Work runs on SelfRepair's worker queue (`agent_repair_step`); when the
queue is unavailable the job fails with that reason, unless SELFREPAIR_AGENT_REPAIR_INLINE allows running it here.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, ValidationError

from selfrepair.agent_repair import workspace as ws
from selfrepair.agent_repair.auth import ServiceCaller, service_caller
from selfrepair.agent_repair.pipeline import run_step
from selfrepair.agent_repair.prs import GitHubPullRequests, PullRequestError
from selfrepair.agent_repair.store import AgentRepairStore, InvalidRepairTransition, as_dict
from selfrepair.api.deps import SessionDep, get_app_sessionmaker

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/agent-repairs", tags=["agent-repair"])
PULL_REQUESTS = GitHubPullRequests   # replaced in tests; production opens drafts on GitHub
Caller = Annotated[ServiceCaller, Depends(service_caller)]
_ID = r"^[A-Za-z0-9._:-]{1,80}$"
_UNPROCESSABLE = 422   # Starlette renamed its constant (…_ENTITY -> …_CONTENT); the number works on both


class RepoIn(BaseModel):
    url: str = Field(min_length=1, max_length=500)
    base_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    ref: str | None = Field(default=None, max_length=200)


class CreateIn(BaseModel):
    source: Literal["langreplay"]
    attempt_id: str = Field(pattern=_ID)
    case_id: str = Field(min_length=1, max_length=200)
    evidence_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    evidence: dict[str, Any]
    repository: RepoIn
    mode: Literal["plan"]
    requested_by: str | None = Field(default=None, max_length=255)


class ApproveIn(BaseModel):
    approved_by: str = Field(min_length=1, max_length=255)
    approved_at: str | None = None
    what: Literal["plan", "retry"]
    scope: list[str] = Field(min_length=1, max_length=100)
    plan_sha256: str | None = None
    retry: int = Field(default=0, ge=0)


class DraftPrIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(max_length=60000)
    draft: Literal[True]
    requested_by: str | None = Field(default=None, max_length=255)
    patch_sha256: str | None = None
    verification_run: str | None = Field(default=None, max_length=80)


class CancelIn(BaseModel):
    reason: str = Field(default="", max_length=500)


def _parse(model: type[BaseModel], caller: ServiceCaller) -> Any:
    try:
        return model.model_validate_json(caller.body or b"{}")
    except ValidationError as exc:
        raise HTTPException(_UNPROCESSABLE, json.loads(exc.json())) from exc


def _evidence_id(evidence: dict[str, Any]) -> str:
    """The id LangReplay gives a package: the sha256 of its canonical JSON without the id itself."""
    body = {k: v for k, v in evidence.items() if k != "evidence_id"}
    text = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _row(store: AgentRepairStore, caller: ServiceCaller, job_id: str):
    try:
        rid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such agent repair") from None
    row = await store.get(caller.settings.org_id, rid)  # type: ignore[arg-type]
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such agent repair")
    return row


async def _dispatch(request: Request, session, store: AgentRepairStore, row, step: str, caller: ServiceCaller) -> None:
    queue = getattr(request.app.state, "queue", None)
    if queue is not None:
        try:
            await queue.enqueue_job("agent_repair_step", str(row.id), step)
            return
        except Exception as exc:
            logger.warning("agent repair %s: enqueue failed: %s", row.id, exc)
    if caller.settings.inline:
        asyncio.get_running_loop().create_task(run_step(get_app_sessionmaker(), row.id, step))
        await store.event(row, "queue", f"running the {step} step in the API process (SELFREPAIR_AGENT_REPAIR_INLINE)")
        await session.commit()
        return
    expected = "planning" if step == "plan" else "implementing"
    if row.state == expected:
        message = "the worker queue (Redis) is unavailable, so nothing ran; start the worker and ask again"
        await store.move(row, "failed", message, level="error", error=message)
        await session.commit()


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create(request: Request, session: SessionDep, caller: Caller) -> dict[str, Any]:
    body: CreateIn = _parse(CreateIn, caller)
    settings = caller.settings
    if not settings.repo_allowed(body.repository.url):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "this repository is not on SELFREPAIR_AGENT_REPAIR_REPOS")
    if body.evidence.get("evidence_id") != body.evidence_id or _evidence_id(body.evidence) != body.evidence_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "the evidence package does not match its evidence_id")
    if body.evidence.get("case", {}).get("id") != body.case_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "the evidence package is for another case")
    store = AgentRepairStore(session)
    existing = await store.by_attempt(settings.org_id, body.attempt_id)  # type: ignore[arg-type]
    if existing is not None:
        if existing.evidence_id != body.evidence_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "this attempt was already submitted with other evidence")
        return {"job_id": str(existing.id), "state": existing.state, "evidence_id": existing.evidence_id, "gitpilot_run_id": existing.gitpilot_task_id}
    row = await store.create(org_id=settings.org_id, source=body.source, attempt_id=body.attempt_id, case_id=body.case_id,
                             evidence_id=body.evidence_id, evidence=body.evidence, repo_url=body.repository.url,
                             base_commit=body.repository.base_commit, ref=body.repository.ref, requested_by=body.requested_by)
    await store.audit(row, f"langreplay:{body.requested_by or 'unknown'}", "agent_repair.create",
                      {"attempt_id": body.attempt_id, "case_id": body.case_id, "evidence_id": body.evidence_id,
                       "repo_url": body.repository.url, "base_commit": body.repository.base_commit}, ip=caller.ip)
    await session.commit()
    await _dispatch(request, session, store, row, "plan", caller)
    return {"job_id": str(row.id), "state": row.state, "evidence_id": row.evidence_id, "gitpilot_run_id": None}


@router.get("/{job_id}")
async def get(job_id: str, session: SessionDep, caller: Caller) -> dict[str, Any]:
    return as_dict(await _row(AgentRepairStore(session), caller, job_id))


@router.get("/{job_id}/events")
async def events(job_id: str, session: SessionDep, caller: Caller, after: int = 0) -> dict[str, Any]:
    store = AgentRepairStore(session)
    row = await _row(store, caller, job_id)
    items = await store.events(row, after=max(after, 0))
    return {"items": [{"seq": e.seq, "at": e.ts.isoformat() if e.ts else None, "stage": e.stage, "level": e.level, "message": e.message}
                      for e in items], "next": items[-1].seq if items else after}


@router.post("/{job_id}/approve")
async def approve(request: Request, job_id: str, session: SessionDep, caller: Caller) -> dict[str, Any]:
    body: ApproveIn = _parse(ApproveIn, caller)
    store = AgentRepairStore(session)
    row = await _row(store, caller, job_id)
    planned = list((row.plan or {}).get("files") or [])
    if body.what == "plan" and row.state != "plan_ready":
        raise HTTPException(status.HTTP_409_CONFLICT, f"the job is {row.state}: only a ready plan can be approved")
    if body.what == "retry":
        if row.state not in ("patch_ready", "failed") or not row.plan:
            raise HTTPException(status.HTTP_409_CONFLICT, f"the job is {row.state}: a retry needs an approved plan and a finished implementation")
        if body.retry != row.retries + 1 or body.retry > caller.settings.max_retries:
            raise HTTPException(status.HTTP_409_CONFLICT, f"retry {body.retry} is not allowed (done: {row.retries}, at most {caller.settings.max_retries})")
    outside = [p for p in body.scope if p not in planned and not any(p.startswith(f) for f in planned if f.endswith("/"))]
    if outside:
        raise HTTPException(_UNPROCESSABLE, f"the scope may only narrow the plan's files; not in the plan: {', '.join(outside)}")
    try:
        ws.check_paths(body.scope, body.scope)      # no absolute path, no `..`, nothing forbidden
    except ws.WorkspaceError as exc:
        raise HTTPException(_UNPROCESSABLE, str(exc)) from exc
    try:
        await store.move(row, "implementing", f"{body.what} approved by {body.approved_by} within {', '.join(body.scope)}",
                         payload={"approved_by": body.approved_by, "scope": body.scope, "plan_sha256": body.plan_sha256},
                         scope=body.scope, approved_by=body.approved_by, retries=body.retry if body.what == "retry" else row.retries,
                         cancel_requested=False, error=None)
    except InvalidRepairTransition as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await store.audit(row, f"langreplay:{body.approved_by}", "agent_repair.approve",
                      {"what": body.what, "scope": body.scope, "plan_sha256": body.plan_sha256, "retry": body.retry}, ip=caller.ip)
    await session.commit()
    await _dispatch(request, session, store, row, "implement", caller)
    return {"job_id": str(row.id), "state": row.state}


@router.post("/{job_id}/draft-pr")
async def draft_pr(job_id: str, session: SessionDep, caller: Caller) -> dict[str, Any]:
    body: DraftPrIn = _parse(DraftPrIn, caller)
    store = AgentRepairStore(session)
    row = await _row(store, caller, job_id)
    if row.state != "patch_ready":
        raise HTTPException(status.HTTP_409_CONFLICT, f"the job is {row.state}: a draft PR needs a ready patch")
    checks = (row.static_checks or {}).get("status")
    if checks == "not_configured":
        raise HTTPException(status.HTTP_409_CONFLICT, "no static check is configured (SELFREPAIR_AGENT_REPAIR_CHECKS): a draft PR needs at least one that passed")
    if checks != "passed":
        raise HTTPException(status.HTTP_409_CONFLICT, "the static checks did not pass on this patch")
    if not body.patch_sha256 or body.patch_sha256 != row.patch_sha256:
        raise HTTPException(status.HTTP_409_CONFLICT, "patch_sha256 does not match the patch SelfRepair produced: LangReplay verified another patch")
    if not body.verification_run:
        raise HTTPException(status.HTTP_409_CONFLICT, "a draft PR needs the LangReplay verification run that measured this patch")
    token = caller.settings.github_token
    if not token:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "SELFREPAIR_AGENT_REPAIR_GITHUB_TOKEN is not set: no branch can be pushed")
    opener = PULL_REQUESTS(token)
    folder = ws.root() / f"{row.id}-pr"
    branch = row.branch or f"langreplay/{row.attempt_id}"
    try:
        await asyncio.to_thread(ws.clone_at, row.repo_url, row.base_commit, folder)
        await asyncio.to_thread(ws.apply_patch, folder, row.patch or "")
        head = await asyncio.to_thread(ws.push_branch, folder, branch=branch, remote_url=row.repo_url, token=token,
                                       message=f"LangReplay repair {row.attempt_id} for case {row.case_id}\n\nVerified run: {body.verification_run}")
        pr = await asyncio.to_thread(opener.open_draft, repo_url=row.repo_url, head=branch, base=row.ref or "main",
                                     title=body.title, body=body.body)
    except (ws.WorkspaceError, PullRequestError) as exc:
        await store.event(row, "pr", f"draft PR not opened: {exc}", level="error")
        await session.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    finally:
        await asyncio.to_thread(ws.remove, folder)
    await store.move(row, "pr_draft", f"draft PR #{pr.get('number')} opened from {branch}", payload={"head": head, "url": pr["url"]},
                     pr_url=pr["url"], pr_number=pr.get("number"), verification_run=body.verification_run)
    await store.audit(row, f"langreplay:{body.requested_by or 'unknown'}", "agent_repair.draft_pr",
                      {"url": pr["url"], "branch": branch, "head": head, "verification_run": body.verification_run}, ip=caller.ip)
    await session.commit()
    return {"url": pr["url"], "number": pr.get("number"), "draft": True}


@router.post("/{job_id}/cancel")
async def cancel(job_id: str, session: SessionDep, caller: Caller) -> dict[str, Any]:
    body: CancelIn = _parse(CancelIn, caller)
    store = AgentRepairStore(session)
    row = await _row(store, caller, job_id)
    try:
        await store.move(row, "cancelled", f"cancelled: {body.reason or 'no reason given'}", cancel_requested=True)
    except InvalidRepairTransition as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    await store.audit(row, "langreplay", "agent_repair.cancel", {"reason": body.reason}, ip=caller.ip)
    await session.commit()
    return {"job_id": str(row.id), "state": row.state}

