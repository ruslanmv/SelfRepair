"""Dependency / packaging analyzer.

Checks for pyproject.toml presence and obvious dependency-declaration issues.
Pure-diagnostic: never writes files. Returns detector-shaped issues.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:  # Python 3.11+ has tomllib in the stdlib.
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - py<3.11 fallback
    tomllib = None  # type: ignore[assignment]

from selfrepair.analyzers.repo_analyzer import Issue


@dataclass
class DependencyAnalysis:
    has_pyproject: bool
    declares_dependencies: bool
    issues: list[Issue]


def analyze_dependencies(repo_dir: str | Path) -> DependencyAnalysis:
    repo = Path(repo_dir)
    pyproject = repo / "pyproject.toml"
    requirements = repo / "requirements.txt"
    issues: list[Issue] = []

    if not pyproject.exists():
        issues.append(
            Issue(
                id="missing-pyproject",
                severity="high",
                description="No pyproject.toml found at the repository root.",
                recommended_action="Add a pyproject.toml declaring build-system and project metadata.",
            )
        )
        # A bare requirements.txt is acceptable but worth flagging as info.
        return DependencyAnalysis(False, requirements.exists(), issues)

    declares_dependencies = False
    if tomllib is not None:
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            issues.append(
                Issue(
                    id="invalid-pyproject",
                    severity="medium",
                    description="pyproject.toml is present but could not be parsed as valid TOML.",
                    recommended_action="Fix the TOML syntax in pyproject.toml.",
                )
            )
            return DependencyAnalysis(True, False, issues)

        project = data.get("project", {})
        deps = project.get("dependencies")
        declares_dependencies = bool(deps)
        if "project" not in data and "tool" not in data:
            issues.append(
                Issue(
                    id="incomplete-pyproject",
                    severity="low",
                    description="pyproject.toml lacks a [project] or [tool] section.",
                    recommended_action="Add a [project] table with name, version and dependencies.",
                )
            )
        elif project and not project.get("name"):
            issues.append(
                Issue(
                    id="incomplete-pyproject",
                    severity="low",
                    description="[project] table in pyproject.toml is missing a `name`.",
                    recommended_action="Add a `name` field to the [project] table.",
                )
            )

    return DependencyAnalysis(True, declares_dependencies, issues)
