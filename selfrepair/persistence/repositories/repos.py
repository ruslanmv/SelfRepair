"""Repository for the `repo` inventory table.

Produces both raw rows (for the worker) and aggregate-rich summaries
(for the operator console). The console list endpoint must page over
thousands of repos cheaply, so the count subqueries are folded into a
single outer-joined select rather than N+1 follow-ups.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.persistence.models import (
    Finding,
    FindingStatus,
    Job,
    Repair,
    Repo,
)


@dataclass(frozen=True)
class RepoWithCounts:
    """`Repo` plus the aggregates the console renders next to its name."""

    repo: Repo
    open_findings: int
    repair_count: int
    last_job_at: datetime | None


class ReposRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --------------------------- writes (worker) ---------------------------

    async def upsert(
        self,
        *,
        org_id: uuid.UUID,
        provider: str,
        full_name: str,
        default_branch: str = "main",
        last_seen_sha: str | None = None,
        config_yaml: str | None = None,
    ) -> Repo:
        stmt = (
            pg_insert(Repo)
            .values(
                org_id=org_id,
                provider=provider,
                full_name=full_name,
                default_branch=default_branch,
                last_seen_sha=last_seen_sha,
                config_yaml=config_yaml,
            )
            .on_conflict_do_update(
                index_elements=["org_id", "provider", "full_name"],
                set_={
                    "default_branch": default_branch,
                    "last_seen_sha": last_seen_sha,
                    "config_yaml": config_yaml,
                },
            )
            .returning(Repo)
        )
        return (await self._session.execute(stmt)).scalar_one()

    # --------------------------- reads (api) -------------------------------

    async def get(self, repo_id: uuid.UUID) -> Repo | None:
        return await self._session.get(Repo, repo_id)

    async def get_for_org(
        self, repo_id: uuid.UUID, org_id: uuid.UUID
    ) -> Repo | None:
        """Object-level scope check: returns the repo only if it belongs to the org.

        Routes always go through this on the detail surface so a caller
        can never read a repo from another tenant by guessing UUIDs.
        """
        stmt = select(Repo).where(Repo.id == repo_id, Repo.org_id == org_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_active_for_org(self, org_id: uuid.UUID) -> list[Repo]:
        stmt = (
            select(Repo)
            .where(Repo.org_id == org_id, Repo.archived_at.is_(None))
            .order_by(Repo.full_name)
        )
        return list((await self._session.execute(stmt)).scalars())

    async def list_with_counts(
        self,
        *,
        org_id: uuid.UUID,
        q: str | None = None,
        provider: str | None = None,
        include_archived: bool = False,
        limit: int = 50,
        after_full_name: str | None = None,
    ) -> list[RepoWithCounts]:
        """Page over repos with denormalised aggregates.

        Pagination uses a `(full_name, id)`-style keyset over `full_name`
        — the natural ordering for a console table — to stay stable as
        rows are inserted/archived. `limit` is the page size; callers ask
        for `limit + 1` upstream when they want to detect a next page.
        """
        of_sq = (
            select(
                Finding.repo_id.label("repo_id"),
                func.count(Finding.id).label("c"),
            )
            .where(
                Finding.org_id == org_id,
                Finding.status == FindingStatus.OPEN,
            )
            .group_by(Finding.repo_id)
            .subquery()
        )
        rc_sq = (
            select(
                Job.repo_id.label("repo_id"),
                func.count(Repair.id).label("c"),
            )
            .join(Repair, Repair.job_id == Job.id)
            .where(Job.org_id == org_id)
            .group_by(Job.repo_id)
            .subquery()
        )
        lj_sq = (
            select(
                Job.repo_id.label("repo_id"),
                func.max(Job.started_at).label("c"),
            )
            .where(Job.org_id == org_id)
            .group_by(Job.repo_id)
            .subquery()
        )
        stmt = (
            select(
                Repo,
                func.coalesce(of_sq.c.c, 0).label("open_findings"),
                func.coalesce(rc_sq.c.c, 0).label("repair_count"),
                lj_sq.c.c.label("last_job_at"),
            )
            .outerjoin(of_sq, of_sq.c.repo_id == Repo.id)
            .outerjoin(rc_sq, rc_sq.c.repo_id == Repo.id)
            .outerjoin(lj_sq, lj_sq.c.repo_id == Repo.id)
            .where(Repo.org_id == org_id)
            .order_by(Repo.full_name, Repo.id)
            .limit(limit)
        )
        if not include_archived:
            stmt = stmt.where(Repo.archived_at.is_(None))
        if provider:
            stmt = stmt.where(Repo.provider == provider)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(Repo.full_name.ilike(like))
        if after_full_name is not None:
            stmt = stmt.where(Repo.full_name > after_full_name)

        rows = (await self._session.execute(stmt)).all()
        return [
            RepoWithCounts(
                repo=r,
                open_findings=int(of or 0),
                repair_count=int(rc or 0),
                last_job_at=lj,
            )
            for (r, of, rc, lj) in rows
        ]

    async def summary_for(
        self, *, repo_id: uuid.UUID, org_id: uuid.UUID
    ) -> RepoWithCounts | None:
        """Per-repo aggregate. Returns None if the repo isn't in the org."""
        of_sq = (
            select(func.count(Finding.id))
            .where(
                Finding.org_id == org_id,
                Finding.repo_id == repo_id,
                Finding.status == FindingStatus.OPEN,
            )
            .scalar_subquery()
        )
        rc_sq = (
            select(func.count(Repair.id))
            .select_from(Repair)
            .join(Job, Job.id == Repair.job_id)
            .where(Job.org_id == org_id, Job.repo_id == repo_id)
            .scalar_subquery()
        )
        lj_sq = (
            select(func.max(Job.started_at))
            .where(Job.org_id == org_id, Job.repo_id == repo_id)
            .scalar_subquery()
        )
        stmt = select(
            Repo,
            of_sq.label("open_findings"),
            rc_sq.label("repair_count"),
            lj_sq.label("last_job_at"),
        ).where(Repo.id == repo_id, Repo.org_id == org_id)

        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        repo, of, rc, lj = row
        return RepoWithCounts(
            repo=repo,
            open_findings=int(of or 0),
            repair_count=int(rc or 0),
            last_job_at=lj,
        )
