"""CI workflow analyzer.

Inspects ``.github/workflows`` for the presence and basic YAML validity of CI
workflows. Pure-diagnostic: it never writes files. Returns detector-shaped
issues ({id, severity, description, recommended_action}).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from selfrepair.analyzers.repo_analyzer import Issue


@dataclass
class CIAnalysis:
    has_workflows: bool
    workflow_files: list[str]
    invalid_files: list[str]
    issues: list[Issue]


def analyze_ci(repo_dir: str | Path) -> CIAnalysis:
    repo = Path(repo_dir)
    workflows_dir = repo / ".github" / "workflows"
    workflow_files: list[str] = []
    invalid_files: list[str] = []
    issues: list[Issue] = []

    if not workflows_dir.is_dir():
        issues.append(
            Issue(
                id="missing-ci-workflow",
                severity="medium",
                description="No CI workflow directory (.github/workflows) found.",
                recommended_action="Add a GitHub Actions workflow that installs deps and runs tests.",
            )
        )
        return CIAnalysis(False, [], [], issues)

    for path in sorted(workflows_dir.iterdir()):
        if path.suffix not in (".yml", ".yaml"):
            continue
        rel = str(path.relative_to(repo))
        workflow_files.append(rel)
        try:
            parsed = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
            if not isinstance(parsed, dict) or not parsed.get("jobs"):
                invalid_files.append(rel)
        except Exception:
            invalid_files.append(rel)

    if not workflow_files:
        issues.append(
            Issue(
                id="missing-ci-workflow",
                severity="medium",
                description="`.github/workflows` exists but contains no workflow files.",
                recommended_action="Add at least one .yml workflow under .github/workflows/.",
            )
        )
    for rel in invalid_files:
        issues.append(
            Issue(
                id="invalid-ci-workflow",
                severity="low",
                description=f"CI workflow {rel} is not valid (unparseable or missing jobs).",
                recommended_action=f"Fix the YAML and ensure {rel} defines a `jobs:` section.",
            )
        )

    return CIAnalysis(
        has_workflows=bool(workflow_files),
        workflow_files=workflow_files,
        invalid_files=invalid_files,
        issues=issues,
    )
