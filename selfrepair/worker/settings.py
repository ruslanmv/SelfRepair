"""Worker runtime settings sourced from env (`SELFREPAIR_*`)."""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SELFREPAIR_", extra="ignore")

    database_url: str = Field(
        default="postgresql+asyncpg://selfrepair:selfrepair@localhost/selfrepair"
    )
    redis_url: str = Field(default="redis://localhost:6379/0")
    gitpilot_url: str = Field(default="http://gitpilot:8000")
    gitpilot_token: str = Field(default="")
    ollabridge_url: str = Field(default="http://ollabridge:7860")
    # Default to /tmp so unit tests and laptop dev don't need sudo. Production
    # Docker/Kubernetes overrides this with `SELFREPAIR_SANDBOX_WORKDIR`.
    sandbox_workdir: str = Field(default="/tmp/selfrepair/sandbox")
    job_max_attempts: int = Field(default=3, ge=1, le=10)
    job_timeout_seconds: int = Field(default=1800, ge=60)


def get_worker_settings() -> WorkerSettings:
    return WorkerSettings()
