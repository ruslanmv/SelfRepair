from __future__ import annotations

from pathlib import Path

from selfrepair.gitpilot.patcher import apply_safe_local_fixes
from selfrepair.models import RepoHealthReport


def apply_fixes(report: RepoHealthReport, repo_dir: Path) -> list[str]:
    return apply_safe_local_fixes(report, repo_dir)
