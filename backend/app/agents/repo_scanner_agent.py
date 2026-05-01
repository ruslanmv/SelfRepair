from __future__ import annotations

from pathlib import Path

from backend.app.agents.issue_classifier_agent import IssueClassifierAgent
from backend.app.schemas.scan_result import ScanResult
from selfrepair.analyzers.repo_analyzer import analyze_repo_layout
from selfrepair.models import RepoHealthReport, RepoRef


class RepoScannerAgent:
    """Scans repository structure and delivery-readiness signals."""

    def run(self, repo: RepoRef, repo_path: str | Path) -> tuple[RepoHealthReport, ScanResult]:
        repo_dir = Path(repo_path)
        report = RepoHealthReport(repo=repo)
        analyze_repo_layout(report, repo_dir)
        issues = IssueClassifierAgent().run(report)
        score = _score_report(report)
        return report, ScanResult(
            repo=repo.full_name,
            repo_path=str(repo_dir),
            repo_type=report.repo_type,
            platform=repo.platform,
            checks={check.name: check.ok for check in report.checks},
            issues=issues,
            issues_found=len(issues),
            health_score_before=score,
        )


def _score_report(report: RepoHealthReport) -> int:
    if not report.checks:
        return 0
    passed = sum(1 for check in report.checks if check.ok)
    return round((passed / len(report.checks)) * 100)
