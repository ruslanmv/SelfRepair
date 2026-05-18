"""`/v1/repos` — inventory listing, detail, and sync mutation.

The SPA's read needs (list, detail, summary, config) + a single
mutation (`/sync`) that hands off to the worker. Create / patch /
delete are deferred to a follow-up batch.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel

from selfrepair.api.deps import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    CtxDep,
    SessionDep,
    encode_cursor,
)
from selfrepair.persistence.models import Repo
from selfrepair.persistence.repositories.audit import AuditRepository
from selfrepair.persistence.repositories.repos import (
    ReposRepository,
    RepoWithCounts,
)

router = APIRouter(prefix="/v1/repos", tags=["repos"])


_HEALTH_PENALTY_PER_FINDING = 5


def _health_score(open_findings: int) -> int:
    return max(0, min(100, 100 - _HEALTH_PENALTY_PER_FINDING * open_findings))


def _serialize_repo(repo: Repo) -> dict[str, Any]:
    return {
        "id": str(repo.id),
        "org_id": str(repo.org_id),
        "provider": repo.provider,
        "full_name": repo.full_name,
        "default_branch": repo.default_branch,
        "last_seen_sha": repo.last_seen_sha,
        "archived_at": (
            repo.archived_at.isoformat() if repo.archived_at else None
        ),
    }


def _serialize_with_counts(item: RepoWithCounts) -> dict[str, Any]:
    base = _serialize_repo(item.repo)
    base.update(
        {
            "open_findings": item.open_findings,
            "repair_count": item.repair_count,
            "last_job_at": (
                item.last_job_at.isoformat() if item.last_job_at else None
            ),
            "health_score": _health_score(item.open_findings),
        }
    )
    return base


@router.get("")
async def list_repos(
    ctx: CtxDep,
    session: SessionDep,
    q: str | None = Query(default=None, max_length=255),
    provider: str | None = Query(default=None, max_length=32),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = Query(default=None),
) -> dict[str, Any]:
    after_full_name: str | None = None
    if cursor:
        from selfrepair.api.deps import decode_cursor

        after_full_name = decode_cursor(cursor).get("after_full_name")
    repo = ReposRepository(session)
    rows = await repo.list_with_counts(
        org_id=ctx.org_id,
        q=q,
        provider=provider,
        include_archived=include_archived,
        limit=limit + 1,
        after_full_name=after_full_name,
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = (
        encode_cursor({"after_full_name": page[-1].repo.full_name})
        if has_more and page
        else None
    )
    return {
        "items": [_serialize_with_counts(r) for r in page],
        "count": len(page),
        "next_cursor": next_cursor,
    }


@router.get("/{repo_id}")
async def get_repo(
    repo_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    repo = await ReposRepository(session).get_for_org(repo_id, ctx.org_id)
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="repo not found"
        )
    return {**_serialize_repo(repo), "config_yaml": repo.config_yaml}


@router.get("/{repo_id}/summary")
async def get_repo_summary(
    repo_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    item = await ReposRepository(session).summary_for(
        repo_id=repo_id, org_id=ctx.org_id
    )
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="repo not found"
        )
    return _serialize_with_counts(item)


@router.get("/{repo_id}/config")
async def get_repo_config(
    repo_id: uuid.UUID,
    ctx: CtxDep,
    session: SessionDep,
) -> dict[str, Any]:
    repo = await ReposRepository(session).get_for_org(repo_id, ctx.org_id)
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="repo not found"
        )
    return {
        "repo_id": str(repo.id),
        "config_yaml": repo.config_yaml or "",
    }


# ----------------------------- mutations -----------------------------


class SyncBody(BaseModel):
    repo_id: uuid.UUID | None = None


@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
async def sync_repos(
    body: SyncBody,
    ctx: CtxDep,
    session: SessionDep,
    request: Request,
) -> dict[str, Any]:
    """Enqueue a provider-side resync.

    With no body the API enqueues a fleet-wide resync; with `repo_id`
    set it scopes to a single repo. Audit row is recorded synchronously
    so a queued resync that the worker drops is still attributable.
    """
    if body.repo_id is not None:
        repo = await ReposRepository(session).get_for_org(
            body.repo_id, ctx.org_id
        )
        if repo is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="repo not found"
            )
    await AuditRepository(session).record(
        org_id=ctx.org_id,
        actor=ctx.actor or "console",
        action="repo.sync",
        target_type="repo",
        target_id=str(body.repo_id) if body.repo_id else "all",
    )
    await session.commit()
    queue = getattr(request.app.state, "queue", None)
    if queue is not None:
        try:
            await queue.enqueue_job(
                "sync_repo",
                str(body.repo_id) if body.repo_id else None,
            )
        except Exception:
            pass
    return {
        "status": "queued",
        "repo_id": str(body.repo_id) if body.repo_id else None,
    }
