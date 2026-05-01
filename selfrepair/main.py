from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from selfrepair.analyzers.repo_analyzer import analyze_repo_layout
from selfrepair.governance.branch_rules import build_branch_name
from selfrepair.governance.policy_engine import evaluate_policy
from selfrepair.healing.healing_loop import run_healing_loop
from selfrepair.inventory.filters import include_repo
from selfrepair.inventory.huggingface_discovery import HuggingFaceDiscovery
from selfrepair.inventory.github_discovery import GitHubOrgDiscovery
from selfrepair.inventory.gitlab_discovery import GitLabDiscovery
from selfrepair.inventory.repo_inventory import save_inventory
from selfrepair.matrixlab.sandbox import SandboxManager
from selfrepair.models import RepoHealthReport, RepoRef
from selfrepair.reporting.history_builder import write_history
from selfrepair.site.generator import generate_site
from selfrepair.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def push_repair_branch(repo_dir: Path, report: RepoHealthReport, settings: Settings) -> None:
    if not report.changed_files:
        return
    branch = report.branch_name or build_branch_name(report.repo.name)
    report.branch_name = branch
    if settings.dry_run:
        report.notes.append("dry_run=true; branch push skipped")
        report.pushed_branch = branch
        return
    subprocess.run(["git", "checkout", "-B", branch], cwd=repo_dir, check=False, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=False, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", f"SelfRepair Repo repair for {report.repo.full_name}"], cwd=repo_dir, check=False, capture_output=True, text=True)
    subprocess.run(["git", "push", "-u", "origin", branch], cwd=repo_dir, check=False, capture_output=True, text=True)
    report.pushed_branch = branch


def collect_repositories(settings: Settings) -> list[RepoRef]:
    repos: list[RepoRef] = []
    repos.extend(GitHubOrgDiscovery(settings).list_repositories())
    repos.extend(HuggingFaceDiscovery(settings).list_repositories())
    repos.extend(GitLabDiscovery(settings).list_repositories())
    return [repo for repo in repos if include_repo(repo)]


def check_single_repo(repo: RepoRef, settings: Settings) -> RepoHealthReport:
    sandbox = SandboxManager(settings)
    repo_dir = sandbox.clone_repo(repo)
    report = RepoHealthReport(repo=repo, branch_name=build_branch_name(repo.name))
    analyze_repo_layout(report, repo_dir)
    report = run_healing_loop(report, repo_dir, settings)
    policy = evaluate_policy(report.changed_files)
    report.notes.append(f"policy_risk={policy['risk']}")
    if report.status == "healthy" and report.changed_files:
        push_repair_branch(repo_dir, report, settings)
    return report


def run_daily(settings: Settings) -> list[RepoHealthReport]:
    repos = collect_repositories(settings)
    save_inventory(settings, repos)

    reports: list[RepoHealthReport] = []
    for repo in repos:
        try:
            reports.append(check_single_repo(repo, settings))
        except Exception as exc:
            report = RepoHealthReport(repo=repo, status="down")
            report.notes.append(f"unhandled_error={exc}")
            report.finalize_status()
            reports.append(report)

    latest_path = settings.state_dir / "latest_status.json"
    latest_path.write_text(json.dumps({"items": [r.model_dump(mode="json") for r in reports]}, indent=2), encoding="utf-8")
    write_history(settings.state_dir / "history_index.json", reports)
    generate_site(settings)
    return reports


def run_daily_main() -> int:
    settings = get_settings()
    run_daily(settings)
    return 0
