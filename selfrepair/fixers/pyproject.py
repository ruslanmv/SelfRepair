"""PyProject fixer: requires-python >= 3.11 and a [tool.uv] section.

Text-based for predictability. Round-tripping comments via tomlkit would be
nicer but adds a dep for one fixer; the regex approach handles the cases
that actually appear in the inventory.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from selfrepair.fixers._diff import make_unified_diff, read_existing
from selfrepair.sdk.models import (
    Finding,
    Patch,
    RepairPlan,
    RepoContext,
    Severity,
)

_DEFAULT_PYPROJECT = """\
[project]
name = "{name}"
version = "0.1.0"
requires-python = ">=3.11,<3.13"
dependencies = []

[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[tool.uv]
dev-dependencies = []
"""

_REQUIRES_PY_RE = re.compile(
    r'^(\s*requires-python\s*=\s*)(["\'])([^"\']*)\2',
    re.MULTILINE,
)


@dataclass(frozen=True)
class PyProjectFixer:
    id: str = "py.pyproject"
    handles: tuple[str, ...] = (
        "pyproject_missing",
        "pyproject_python_version",
        "pyproject_uv_missing",
    )
    risk: Severity = Severity.LOW

    def matches(self, finding: Finding, ctx: RepoContext) -> bool:
        return finding.kind in self.handles

    def plan(self, finding: Finding, ctx: RepoContext) -> RepairPlan:
        summaries = {
            "pyproject_missing": "Create pyproject.toml with Python 3.11+ and uv",
            "pyproject_python_version": "Set requires-python to >=3.11",
            "pyproject_uv_missing": "Add [tool.uv] section to pyproject.toml",
        }
        return RepairPlan(
            fixer_id=self.id,
            finding=finding,
            summary=summaries.get(finding.kind, "Update pyproject.toml"),
            risk=self.risk,
            files_touched=("pyproject.toml",),
        )

    def apply(self, plan: RepairPlan, ctx: RepoContext) -> Patch:
        before = read_existing(ctx.workspace, "pyproject.toml")
        if not before.strip():
            name = ctx.full_name.split("/")[-1] or "project"
            after = _DEFAULT_PYPROJECT.format(name=name)
        else:
            after = before
            kind = plan.finding.kind
            if kind in ("pyproject_python_version", "pyproject_missing"):
                after = _ensure_python_version(after)
            if kind in ("pyproject_uv_missing", "pyproject_missing"):
                after = _ensure_uv_section(after)
        diff = make_unified_diff(
            file_path="pyproject.toml", before=before, after=after
        )
        return Patch(
            fixer_id=self.id,
            finding_fingerprint=plan.finding.fingerprint,
            diff=diff,
            files_changed=("pyproject.toml",) if diff else (),
            summary=plan.summary,
        )


def _ensure_python_version(content: str) -> str:
    if _REQUIRES_PY_RE.search(content):
        return _REQUIRES_PY_RE.sub(
            lambda m: f'{m.group(1)}{m.group(2)}>=3.11,<3.13{m.group(2)}',
            content,
            count=1,
        )
    project_idx = content.find("[project]")
    if project_idx == -1:
        return content + '\n[project]\nrequires-python = ">=3.11,<3.13"\n'
    insertion_point = content.find("\n", project_idx) + 1
    return (
        content[:insertion_point]
        + 'requires-python = ">=3.11,<3.13"\n'
        + content[insertion_point:]
    )


def _ensure_uv_section(content: str) -> str:
    if "[tool.uv]" in content:
        return content
    suffix = "" if content.endswith("\n") else "\n"
    return content + suffix + "\n[tool.uv]\ndev-dependencies = []\n"
