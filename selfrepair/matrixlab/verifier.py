from __future__ import annotations

from pathlib import Path

from selfrepair.execution.install_runner import run_install
from selfrepair.execution.start_runner import run_start
from selfrepair.execution.test_runner import run_test
from selfrepair.models import RepoHealthReport
from selfrepair.settings import Settings


def verify_repo(report: RepoHealthReport, repo_dir: Path, settings: Settings) -> RepoHealthReport:
    report.install_result = run_install(repo_dir, settings.repo_timeout_seconds)
    report.install_ok = report.install_result.ok
    if not report.install_ok:
        report.notes.append("install step failed")
        report.finalize_status()
        return report

    report.test_result = run_test(repo_dir, settings.repo_timeout_seconds)
    report.test_ok = report.test_result.ok
    if not report.test_ok:
        report.notes.append("test step failed")
        report.finalize_status()
        return report

    report.start_result = run_start(repo_dir, settings.start_timeout_seconds)
    report.start_ok = report.start_result.ok
    if not report.start_ok:
        report.notes.append("start step failed")

    report.finalize_status()
    return report
