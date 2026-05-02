"""Fixer protocol — the public extension point."""
from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Protocol, runtime_checkable

from selfrepair.sdk.models import Finding, Patch, RepairPlan, RepoContext, Severity

logger = logging.getLogger(__name__)


@runtime_checkable
class Fixer(Protocol):
    """Plugins implement this to register a deterministic repair.

    Lifecycle: matches → plan → (policy review) → apply.

    Implementations MUST be pure within `plan()` (no I/O outside the workspace).
    Implementations MUST NOT call out to any LLM — the LLM tier is escalated to
    GitPilot by the worker, not by individual fixers (ADR-0001).
    """

    id: str
    handles: tuple[str, ...]
    risk: Severity

    def matches(self, finding: Finding, ctx: RepoContext) -> bool: ...

    def plan(self, finding: Finding, ctx: RepoContext) -> RepairPlan: ...

    def apply(self, plan: RepairPlan, ctx: RepoContext) -> Patch: ...


class FixerRegistry:
    """Lookup of registered fixers, indexed by finding kind."""

    def __init__(self) -> None:
        self._fixers: list[Fixer] = []

    def register(self, fixer: Fixer) -> None:
        if not isinstance(fixer, Fixer):
            raise TypeError(f"{fixer!r} does not implement the Fixer protocol")
        for existing in self._fixers:
            if existing.id == fixer.id:
                raise ValueError(f"Fixer {fixer.id!r} already registered")
        self._fixers.append(fixer)
        logger.info("registered fixer %s (handles=%s)", fixer.id, fixer.handles)

    def candidates_for(self, finding: Finding, ctx: RepoContext) -> Iterable[Fixer]:
        for fixer in self._fixers:
            if finding.kind in fixer.handles and fixer.matches(finding, ctx):
                yield fixer

    def __len__(self) -> int:
        return len(self._fixers)
