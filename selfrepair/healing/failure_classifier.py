from __future__ import annotations

from selfrepair.models import RepoHealthReport


def classify_failure(report: RepoHealthReport) -> str:
    for result_name in ("install_result", "test_result", "start_result"):
        result = getattr(report, result_name)
        if result and not result.ok:
            return result_name.replace("_result", "")
    missing = [check.name for check in report.checks if not check.ok]
    return ",".join(missing) if missing else "unknown"
