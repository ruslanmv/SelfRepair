"""Issue Watch runtime knobs read from `SELFREPAIR_*` env.

Mirrors `selfrepair.ci.config`'s shape so the operator-facing experience is
identical: one BaseSettings class, all knobs prefixed `SELFREPAIR_`,
defaults safe for unit tests, the kill switch first.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class IssueWatchRuntime(BaseSettings):
    """Issue Watch runtime config.

    `kill_switch=True` is the safety release valve: the dispatcher and the
    sync task short-circuit and return `ignored` without touching providers.
    """

    model_config = SettingsConfigDict(env_prefix="SELFREPAIR_ISSUES_", extra="ignore")

    kill_switch: bool = Field(default=False)
    sync_window_minutes: int = Field(default=15, ge=1, le=1440)
    page_size: int = Field(default=50, ge=10, le=200)
    request_timeout_seconds: float = Field(default=15.0, ge=1.0, le=120.0)
    huggingface_enabled: bool = Field(default=True)


@lru_cache(maxsize=1)
def get_runtime() -> IssueWatchRuntime:
    return IssueWatchRuntime()
