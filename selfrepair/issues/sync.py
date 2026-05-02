"""Issue Watch worker entrypoint.

Two Arq job functions:

  * `sync_external_issues(repo_id_str | None)` — manual sync, kicked by
    the API's POST /v1/issues/sync. When `repo_id_str` is None we sweep
    every active repo for the org-of-record; otherwise sync just that
    repo. Returns a JSON-serialisable summary the operator can read in
    the worker log.

  * `scheduled_sync_external_issues()` — cron entry that runs every
    `sync_window_minutes` minutes. Same body as the manual sync, but
    always sweeps all repos.

Both delegate to `service.sync_repo_issues` so the orchestration stays in
one place. The kill switch from `selfrepair.issues.config` short-circuits
both before any provider call.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from selfrepair.issues.clients import build_client
from selfrepair.issues.config import get_runtime
from selfrepair.issues.service import sync_repo_issues
from selfrepair.persistence.repositories import IssuesRepository, ReposRepository

logger = logging.getLogger(__name__)


async def sync_external_issues(
    ctx: dict[str, Any], repo_id_str: str | None = None
) -> dict[str, Any]:
    runtime = get_runtime()
    if runtime.kill_switch:
        logger.info("issues sync: kill switch is on; ignoring run")
        return {"status": "ignored", "reason": "kill_switch"}

    sessionmaker = ctx.get("sessionmaker")
    if sessionmaker is None:
        # Defensive: the worker startup wires this; tests can call the
        # function with a sessionmaker in ctx.
        logger.error("issues sync: sessionmaker missing from ctx")
        return {"status": "ignored", "reason": "no_sessionmaker"}

    summaries: list[dict[str, Any]] = []
    async with sessionmaker() as session:
        repos_repo = ReposRepository(session)
        issues_repo = IssuesRepository(session)

        if repo_id_str:
            repo = await repos_repo.get(uuid.UUID(repo_id_str))
            repos = [repo] if repo else []
        else:
            # Phase-1 sweep: every active repo across orgs the worker can see.
            # ReposRepository.list_active_for_org needs an org_id; we don't
            # have one here, so we list per-repo via a session query. This
            # path is intentionally narrow until multi-org sweep lands.
            repos = await _all_active_repos(session)

        for repo in repos:
            if repo is None:
                continue
            report = await sync_repo_issues(
                repo=repo,
                issues_repo=issues_repo,
                client_factory=build_client,
            )
            summaries.append(
                {
                    "repo": report.repo_full_name,
                    "provider": report.provider,
                    "upserted": report.upserted,
                    "closed_reconciled": report.closed_reconciled,
                    "errors": report.errors,
                }
            )

        await session.commit()

    return {"status": "ok", "repos": len(summaries), "summaries": summaries}


async def scheduled_sync_external_issues(
    ctx: dict[str, Any],
) -> dict[str, Any]:
    """Cron entry. Runs the unscoped sync."""
    return await sync_external_issues(ctx, None)


async def _all_active_repos(session: Any) -> list[Any]:
    """Lightweight query for every non-archived repo across orgs.

    Kept here (not on ReposRepository) because the canonical surface is
    org-scoped; this is the worker-side sweep that intentionally crosses
    that boundary. The repo list is bounded by the inventory, so a full
    select is acceptable until we shard.
    """
    from sqlalchemy import select

    from selfrepair.persistence.models import Repo

    stmt = (
        select(Repo)
        .where(Repo.archived_at.is_(None))
        .order_by(Repo.org_id, Repo.full_name)
    )
    return list((await session.execute(stmt)).scalars())
