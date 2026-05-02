"""HealthTest fixer: ensures `tests/test_health.py` exists.

Writes a minimal package-imports check so a successful test run confirms the
package installs and imports cleanly. The check is intentionally generic so
it doesn't depend on project-specific code.
"""
from __future__ import annotations

from dataclasses import dataclass

from selfrepair.fixers._diff import make_unified_diff, read_existing
from selfrepair.sdk.models import (
    Finding,
    Patch,
    RepairPlan,
    RepoContext,
    Severity,
)

_DEFAULT_HEALTH_TEST = '''\
"""Health check: every package next to pyproject.toml imports cleanly."""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def _packages():
    root = Path(__file__).resolve().parents[1]
    if not (root / "pyproject.toml").is_file():
        return
    for candidate in root.iterdir():
        if candidate.is_dir() and (candidate / "__init__.py").is_file():
            yield candidate.name


@pytest.mark.parametrize("pkg", list(_packages()))
def test_package_imports(pkg: str) -> None:
    importlib.import_module(pkg)
'''


@dataclass(frozen=True)
class HealthTestFixer:
    id: str = "py.health_test"
    handles: tuple[str, ...] = ("health_test_missing",)
    risk: Severity = Severity.LOW

    def matches(self, finding: Finding, ctx: RepoContext) -> bool:
        return finding.kind in self.handles

    def plan(self, finding: Finding, ctx: RepoContext) -> RepairPlan:
        return RepairPlan(
            fixer_id=self.id,
            finding=finding,
            summary="Add tests/test_health.py with a package-imports check",
            risk=self.risk,
            files_touched=("tests/test_health.py",),
        )

    def apply(self, plan: RepairPlan, ctx: RepoContext) -> Patch:
        before = read_existing(ctx.workspace, "tests/test_health.py")
        after = before if before.strip() else _DEFAULT_HEALTH_TEST
        diff = make_unified_diff(
            file_path="tests/test_health.py", before=before, after=after
        )
        return Patch(
            fixer_id=self.id,
            finding_fingerprint=plan.finding.fingerprint,
            diff=diff,
            files_changed=("tests/test_health.py",) if diff else (),
            summary=plan.summary,
        )
