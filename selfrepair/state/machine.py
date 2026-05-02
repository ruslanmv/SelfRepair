"""Job state machine.

A repair run is a sequence of explicit transitions through these states.
Every transition is an audit row; retries are idempotent on
`(job_id, stage, repo_sha)`.

See `docs/architecture/system-design.md` §3.
"""
from __future__ import annotations

from enum import StrEnum


class JobState(StrEnum):
    QUEUED = "queued"
    CLONING = "cloning"
    ANALYZING = "analyzing"
    SCANNING = "scanning"
    PLANNING = "planning"
    REPAIRING = "repairing"
    VALIDATING = "validating"
    PUBLISHING = "publishing"
    AWAITING_REVIEW = "awaiting_review"
    COMPLETED = "completed"
    FAILED_VALIDATION = "failed_validation"
    ESCALATED = "escalated"
    MERGED = "merged"
    CLOSED = "closed"
    STALE = "stale"


_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.QUEUED: frozenset({JobState.CLONING, JobState.ESCALATED}),
    JobState.CLONING: frozenset({JobState.ANALYZING, JobState.ESCALATED}),
    JobState.ANALYZING: frozenset({JobState.SCANNING, JobState.ESCALATED}),
    JobState.SCANNING: frozenset({JobState.PLANNING, JobState.ESCALATED}),
    JobState.PLANNING: frozenset(
        {JobState.REPAIRING, JobState.COMPLETED, JobState.ESCALATED}
    ),
    JobState.REPAIRING: frozenset({JobState.VALIDATING, JobState.ESCALATED}),
    JobState.VALIDATING: frozenset(
        {JobState.PUBLISHING, JobState.FAILED_VALIDATION, JobState.ESCALATED}
    ),
    JobState.PUBLISHING: frozenset(
        {JobState.AWAITING_REVIEW, JobState.ESCALATED}
    ),
    JobState.AWAITING_REVIEW: frozenset(
        {JobState.MERGED, JobState.CLOSED, JobState.STALE}
    ),
    JobState.FAILED_VALIDATION: frozenset(
        {JobState.ESCALATED, JobState.CLOSED}
    ),
    JobState.ESCALATED: frozenset({JobState.CLOSED}),
    JobState.STALE: frozenset({JobState.CLOSED}),
    # Terminal
    JobState.COMPLETED: frozenset(),
    JobState.MERGED: frozenset(),
    JobState.CLOSED: frozenset(),
}


class InvalidTransition(ValueError):
    """Raised when a state transition is not allowed by the machine."""


def can_transition(current: JobState, target: JobState) -> bool:
    return target in _TRANSITIONS.get(current, frozenset())


def next_states(current: JobState) -> frozenset[JobState]:
    return _TRANSITIONS.get(current, frozenset())


def assert_transition(current: JobState, target: JobState) -> None:
    if not can_transition(current, target):
        allowed_states = sorted(s.value for s in next_states(current))
        allowed = ", ".join(allowed_states) or "<terminal>"
        raise InvalidTransition(
            f"cannot transition {current.value} → {target.value}; allowed: {allowed}"
        )
