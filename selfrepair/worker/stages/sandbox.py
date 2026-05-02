"""Per-job workspace path helper.

Workspaces live under `WorkerSettings.sandbox_workdir/<job_id>/` so stages
can find each other's outputs without round-tripping through the database.
Deleting the workspace at the end of a job is the operator's responsibility
(today: a cron; tomorrow: a `STALE` cleanup stage).
"""
from __future__ import annotations

import uuid
from pathlib import Path

from selfrepair.worker.settings import get_worker_settings


def workspace_for(job_id: uuid.UUID) -> Path:
    settings = get_worker_settings()
    path = Path(settings.sandbox_workdir) / str(job_id)
    path.mkdir(parents=True, exist_ok=True)
    return path
