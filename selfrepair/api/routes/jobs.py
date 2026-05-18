"""`/v1/jobs` — list, create, detail, events (paginated + SSE), cancel, retry.

The SSE stream replays any events the client missed (via the standard
`Last-Event-ID` header / query param), then forwards live messages from
the Redis pub/sub channel the worker publishes to. A 15-second keepalive
comment is sent on idle connections so intermediaries don't reap them.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from selfrepair.api.deps import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    CtxDep,
    SessionDep,
    decode_cursor,
    encode_cursor,
)
from selfrepair.api.events import KEEPALIVE_SECONDS, subscribe
from selfrepair.persistence.models import Job, JobEvent, JobTrigger, Repo
from selfrepair.persistence.repositories.jobs import (
    ACTIVE_STATES,
    JobsRepository,
)
from selfrepair.persistence.repositories.repos import ReposRepository
from selfrepair.state.machine import JobState

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


def _serialize_job(job: Job) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "org_id": str(job.org_id),
        "repo_id": str(job.repo_id),
        "trigger": (
            job.trigger.value if hasattr(job.trigger, "value") else job.trigger
        ),
        "state": job.state.value if hasattr(job.state, "value") else job.state,
        "started_at": job.started_at.isoformat(),
        "finished_at": (
            job.finished_at.isoformat() if job.finished_at else None
        ),
        "sandbox_id": job.sandbox_id,
        "error_kind": job.error_kind,
    }


def _serialize_repo_lite(r: Repo) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "provider": r.provider,
        "full_name": r.full_name,
        "default_branch": r.default_branch,
    }


def _serialize_with_repo(item: tuple[Job, Repo]) -> dict[str, Any]:
    job, repo = item
    return {**_serialize_job(job), "repo": _serialize_repo_lite(repo)}


def _serialize_event(e: JobEvent) -> dict[str, Any]:
    return {
        "id": e.id,
        "job_id": str(e.job_id),
        "ts": e.ts.isoformat(),
        "stage": e.stage.value if hasattr(e.stage, "value") else e.stage,
        "level": e.level,
        "message": e.message,
        "payload": e.payload,
    }


@router.get("")
async def list_jobs(
    ctx: CtxDep,
    session: SessionDep,
    repo_id: uuid.UUID | None = Query(default=None),
    state: str | None = Query(default=None, max_length=32),
    active_only: bool = Query(default=False),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = Query(default=None),
) -> dict[str, Any]:
    after_started_at: datetime | None = None
    after_id: uuid.UUID | None = None
    if cursor:
        c = decode_cursor(cursor)
        try:
            if c.get("after_started_at"):
                after_started_at = datetime.fromisoformat(c["after_started_at"])
            if c.get("after_id"):
                after_id = uuid.UUID(c["after_id"])
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid cursor payload",
            ) from exc
    parsed_state: JobState | None = None
    if state:
        try:
            parsed_state = JobState(state)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"invalid state: {state}",
            ) from exc

    rows = await JobsRepository(session).list_for_org(
        org_id=ctx.org_id,
        repo_id=repo_id,
        state=parsed_state,
        active_only=active_only,
        limit=limit + 1,
        after_started_at=after_started_at,
        after_id=after_id,
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = (
        encode_cursor(
            {
                "after_started_at": page[-1][0].started_at.isoformat(),
                "after_id": str(page[-1][0].id),
            }
        )
        if has_more and page
        else None
    )
    return {
        "items": [_serialize_with_repo(r) for r in page],
        "count": len(page),
        "next_cursor": next_cursor,
    }


# ---------------------------- create ----------------------------


class CreateJobRequest(BaseModel):
    repo_id: uuid.UUID
    trigger: JobTrigger = Field(default=JobTrigger.MANUAL)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    body: CreateJobRequest,
    ctx: CtxDep,
    session: SessionDep,
    request: Request,
) -> dict[str, Any]:
    repo = await ReposRepository(session).get_for_org(body.repo_id, ctx.org_id)
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="repo not found"
        )
    job = await JobsRepository(session).create(
        org_id=ctx.org_id,
        repo_id=repo.id,
        trigger=body.trigger,
    )
    await session.commit()

    queue = getattr(request.app.state, "queue", None)
    if queue is not None:
        try:
            await queue.enqueue_job("process_job", str(job.id))
        except Exception:
            pass
    return {
        "job_id": str(job.id),
        "state": job.state.value if hasattr(job.state, "value") else job.state,
    }


# ---------------------------- detail ----------------------------


@router.get("/{job_id}")
async def get_job(
    job_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    job = await JobsRepository(session).get_for_org(job_id, ctx.org_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="job not found"
        )
    return _serialize_job(job)


@router.get("/{job_id}/events")
async def list_job_events(
    job_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
    after_id: int | None = Query(default=None, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict[str, Any]:
    repo = JobsRepository(session)
    job = await repo.get_for_org(job_id, ctx.org_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="job not found"
        )
    events = await repo.list_events(
        job_id=job_id, after_id=after_id, limit=limit
    )
    next_after_id = events[-1].id if events else None
    return {
        "items": [_serialize_event(e) for e in events],
        "count": len(events),
        "next_after_id": next_after_id,
    }


# ---------------------------- SSE stream ----------------------------


def _sse_format(event_id: int, data: str) -> str:
    return f"id: {event_id}\ndata: {data}\n\n"


@router.get("/{job_id}/events/stream")
async def stream_job_events(
    job_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
    request: Request,
    last_event_id_header: str | None = Header(
        default=None, alias="Last-Event-ID"
    ),
    last_event_id: int | None = Query(default=None, ge=0, alias="lastEventId"),
) -> StreamingResponse:
    """Server-Sent Events live stream of `job_event` rows.

    The endpoint:
      1. Verifies the job belongs to the caller's org.
      2. Replays any historical events strictly after `last_event_id`
         (header or query param) so reconnects don't drop messages.
      3. Forwards live messages from the worker via Redis pub/sub.
      4. Sends a keepalive comment every 15s so proxies don't time out.
      5. Closes when the client disconnects.
    """
    repo = JobsRepository(session)
    job = await repo.get_for_org(job_id, ctx.org_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="job not found"
        )

    after_id = last_event_id
    if after_id is None and last_event_id_header:
        try:
            after_id = int(last_event_id_header)
        except ValueError:
            after_id = None

    initial = await repo.list_events(
        job_id=job_id, after_id=after_id, limit=500
    )
    initial_serialized = [_serialize_event(e) for e in initial]
    initial_max_id = initial[-1].id if initial else (after_id or 0)

    async def gen():
        # Phase 1: backfill
        for e in initial_serialized:
            yield _sse_format(e["id"], json.dumps(e, default=str))
        # Phase 2: live tail via Redis pub/sub
        try:
            async with subscribe(job_id) as ps:
                next_keepalive = time.monotonic() + KEEPALIVE_SECONDS
                while True:
                    if await request.is_disconnected():
                        return
                    try:
                        msg = await ps.get_message(
                            ignore_subscribe_messages=True, timeout=1.0
                        )
                    except asyncio.CancelledError:
                        return
                    except Exception:
                        # Transient pub/sub error: keep the connection alive
                        # so the client can replay via Last-Event-ID.
                        await asyncio.sleep(0.5)
                        continue
                    if msg and msg.get("data"):
                        try:
                            parsed = json.loads(msg["data"])
                            ev_id = int(parsed.get("id", 0)) or initial_max_id
                        except Exception:
                            ev_id = initial_max_id
                        yield _sse_format(ev_id, msg["data"])
                    if time.monotonic() >= next_keepalive:
                        yield ": keepalive\n\n"
                        next_keepalive = time.monotonic() + KEEPALIVE_SECONDS
        except RuntimeError:
            # redis package missing or unreachable. The replay we already
            # streamed is still useful; a friendly comment lets the client
            # know live tail is unavailable.
            yield ": live-tail-unavailable\n\n"
            return

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------- mutations ----------------------------


@router.post("/{job_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_job(
    job_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    repo = JobsRepository(session)
    job = await repo.get_for_org(job_id, ctx.org_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="job not found"
        )
    if job.state not in ACTIVE_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job is not active (state={job.state.value})",
        )
    actor = ctx.actor or "console"
    await repo.fail(
        job_id=job_id,
        error_kind="cancelled",
        message=f"job cancelled by {actor}",
    )
    await session.commit()
    return {"job_id": str(job_id), "state": JobState.ESCALATED.value}


@router.post("/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_job(
    job_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
    request: Request,
) -> dict[str, Any]:
    repo = JobsRepository(session)
    original = await repo.get_for_org(job_id, ctx.org_id)
    if original is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="job not found"
        )
    new = await repo.create(
        org_id=ctx.org_id,
        repo_id=original.repo_id,
        trigger=JobTrigger.RETRY,
    )
    await session.commit()
    queue = getattr(request.app.state, "queue", None)
    if queue is not None:
        try:
            await queue.enqueue_job("process_job", str(new.id))
        except Exception:
            pass
    return {
        "original_job_id": str(original.id),
        "job_id": str(new.id),
        "state": new.state.value if hasattr(new.state, "value") else new.state,
    }
