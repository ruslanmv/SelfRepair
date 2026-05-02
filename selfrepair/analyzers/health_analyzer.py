from __future__ import annotations

from selfrepair.models import RepoHealthReport


def summarize_health(report: RepoHealthReport) -> str:
    return f"{report.repo.full_name}: {report.status}"
