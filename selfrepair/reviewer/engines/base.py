"""Review engine interface.

Engines read a diff and return findings. They do not publish, merge, or
decide policy. `DeterministicReviewEngine` and `DeepAgentsReviewEngine` are
the two implementations.
"""
from __future__ import annotations

from typing import Protocol

from selfrepair.config.repo_config import ReviewerConfig
from selfrepair.reviewer.schemas import DiffSet, ReviewEvent, ReviewReport


class ReviewEngine(Protocol):
    """A read-only producer of review findings."""

    name: str

    def review(
        self,
        event: ReviewEvent,
        diff: DiffSet,
        config: ReviewerConfig,
    ) -> ReviewReport:
        """Return a report. Raise `EngineUnavailable` when the engine cannot run."""
