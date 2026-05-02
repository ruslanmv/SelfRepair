"""Repository for the `repo` inventory table."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.persistence.models import Repo


class ReposRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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

    async def get(self, repo_id: uuid.UUID) -> Repo | None:
        return await self._session.get(Repo, repo_id)

    async def list_active_for_org(self, org_id: uuid.UUID) -> list[Repo]:
        stmt = (
            select(Repo)
            .where(Repo.org_id == org_id, Repo.archived_at.is_(None))
            .order_by(Repo.full_name)
        )
        return list((await self._session.execute(stmt)).scalars())
