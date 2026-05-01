from __future__ import annotations

from selfrepair.models import RepairPlan, RepoHealthReport


def build_fix_prompt(report: RepoHealthReport, repo_path: str) -> str:
    missing = [check.name for check in report.checks if not check.ok]
    return (
        f"Repair repository {report.repo.full_name} at {repo_path}. "
        f"Missing or failing checks: {', '.join(missing) or 'runtime validation'}. "
        "Keep changes minimal, preserve behavior, and make install/test/start succeed."
    )


def build_repair_plan(report: RepoHealthReport) -> RepairPlan:
    actions = []
    for check in report.checks:
        if not check.ok:
            actions.append(f"Restore {check.name}")
    if not report.install_ok:
        actions.append("Repair installation workflow")
    if not report.test_ok:
        actions.append("Repair test workflow")
    if not report.start_ok:
        actions.append("Repair startup workflow")
    return RepairPlan(summary=f"Repair plan for {report.repo.full_name}", actions=actions or ["No changes required"])
