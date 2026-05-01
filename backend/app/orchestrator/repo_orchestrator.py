from __future__ import annotations

import logging

from backend.app.agents.issue_classifier_agent import IssueClassifierAgent
from backend.app.agents.repair_generation_agent import RepairGenerationAgent
from backend.app.agents.reporting_agent import ReportingAgent
from backend.app.agents.validation_agent import ValidationAgent
from backend.app.services.git_service import GitService
from selfrepair.analyzers.repo_analyzer import analyze_repo_layout
from selfrepair.governance.branch_rules import build_branch_name
from selfrepair.governance.policy_engine import evaluate_policy
from selfrepair.healing.healing_loop import run_healing_loop
from selfrepair.matrixlab.sandbox import SandboxManager
from selfrepair.models import RepoHealthReport
from selfrepair.settings import get_settings

logger = logging.getLogger(__name__)


class RepoOrchestrator:
    """Coordinates the SelfRepair Repo end-to-end workflow."""

    def __init__(self) -> None:
        self.git = GitService()
        self.classifier = IssueClassifierAgent()
        self.repair_generator = RepairGenerationAgent()
        self.validator = ValidationAgent()
        self.reporter = ReportingAgent()

    def run(self, repo_url: str, branch: str = "main", repair_mode: str = "dry_run") -> dict:
        settings = get_settings().model_copy(deep=True)
        settings.dry_run = repair_mode in {"dry_run", "suggest", "safe"} or settings.dry_run
        settings.ensure_directories()

        repo = self.git.build_repo_ref(str(repo_url), branch)

        try:
            repo_dir = SandboxManager(settings).clone_repo(repo)
            initial_report = RepoHealthReport(repo=repo, branch_name=build_branch_name(repo.name))
            analyze_repo_layout(initial_report, repo_dir)
            before_score = _score_checks(initial_report.checks)

            report = run_healing_loop(initial_report, repo_dir, settings)
            policy = evaluate_policy(report.changed_files)
            report.notes.append(f"policy_risk={policy['risk']}")
        except Exception as exc:
            logger.exception("SelfRepair workflow failed for %s", repo_url)
            report = RepoHealthReport(repo=repo, status="down")
            report.notes.append(f"workflow_error={exc}")
            report.finalize_status()

        issues = self.classifier.run(report)
        repair_patches = self.repair_generator.run(issues)
        validation = self.validator.run(report)
        before = locals().get("before_score", _score_checks(report.checks))
        after = _score_after(report)
        final = self.reporter.run(
            report,
            repo_url=str(repo_url),
            branch=branch,
            repair_mode=repair_mode,
            health_score_before=before,
            health_score_after=after,
            issues=issues,
            repair_patches=repair_patches,
            validation=validation,
        )
        return final.model_dump(mode="json")


def _score_checks(checks) -> int:
    if not checks:
        return 0
    return round((sum(1 for check in checks if check.ok) / len(checks)) * 100)


def _score_after(report: RepoHealthReport) -> int:
    if report.status in {"healthy", "repaired"}:
        return 100
    if report.status == "degraded":
        return max(50, _score_checks(report.checks))
    return _score_checks(report.checks)
