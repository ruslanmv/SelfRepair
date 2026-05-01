from __future__ import annotations

from selfrepair.models import RepoHealthReport, SiteSummary


def build_summary(title: str, description: str, reports: list[RepoHealthReport]) -> SiteSummary:
    summary = SiteSummary(title=title, description=description)
    for report in reports:
        if report.status == "healthy":
            summary.healthy += 1
        elif report.status == "degraded":
            summary.degraded += 1
        elif report.status == "down":
            summary.down += 1
        else:
            summary.unknown += 1
    return summary
