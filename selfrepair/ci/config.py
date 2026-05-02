"""Runtime configuration for CI Guardian.

Process-wide knobs sourced from env. The kill switch is the most
important value: setting `SELFREPAIR_CI_GUARDIAN_KILL=1` makes every
dispatch return immediately, which is the safety release valve when
something is misbehaving in production.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class CIGuardianRuntime:
    """Process-wide CI Guardian runtime knobs."""

    kill_switch: bool
    redis_dedupe_ttl_seconds: int
    storm_window_seconds: int
    storm_threshold: int


def get_runtime() -> CIGuardianRuntime:
    """Read knobs from env. Cheap; safe to call per dispatch."""
    return CIGuardianRuntime(
        kill_switch=_truthy(os.getenv("SELFREPAIR_CI_GUARDIAN_KILL", "0")),
        redis_dedupe_ttl_seconds=int(
            os.getenv("SELFREPAIR_CI_DEDUPE_TTL_SECONDS", "86400")
        ),
        storm_window_seconds=int(
            os.getenv("SELFREPAIR_CI_STORM_WINDOW_SECONDS", "3600")
        ),
        storm_threshold=int(os.getenv("SELFREPAIR_CI_STORM_THRESHOLD", "50")),
    )


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}
