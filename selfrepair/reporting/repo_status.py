from __future__ import annotations

from selfrepair.models import RepoHealthReport


def to_repo_item(report: RepoHealthReport) -> dict:
    return {
        "name": report.repo.name,
        "full_name": report.repo.full_name,
        "status": report.status,
        "install_ok": report.install_ok,
        "test_ok": report.test_ok,
        "start_ok": report.start_ok,
        "health_test_ok": report.health_test_ok,
        "fix_attempts": report.fix_attempts,
        "pr_url": report.pr_url,
        "notes": report.notes,
    }
