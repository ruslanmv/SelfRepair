"""Job status endpoints."""
from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from selfrepair.persistence import get_sessionmaker
from selfrepair.persistence.repositories import JobsRepository

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])


async def _session() -> AsyncIterator[AsyncSession]:
    database_url = os.getenv(
        "SELFREPAIR_DATABASE_URL",
        "postgresql+asyncpg://selfrepair:selfrepair@localhost/selfrepair",
    )
    sessionmaker = get_sessionmaker(database_url)
    async with sessionmaker() as session:
        yield session


@router.get("/{job_id}")
async def get_job(
    job_id: uuid.UUID, session: AsyncSession = Depends(_session)
) -> dict[str, str | None]:
    jobs = JobsRepository(session)
    job = await jobs.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="job not found"
        )
    return {
        "id": str(job.id),
        "state": job.state.value,
        "started_at": job.started_at.isoformat(),
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "error_kind": job.error_kind,
    }
