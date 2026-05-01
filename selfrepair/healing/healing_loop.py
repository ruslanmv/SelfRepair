from __future__ import annotations

import logging
from pathlib import Path

from selfrepair.analyzers.repo_analyzer import analyze_repo_layout
from selfrepair.gitpilot.client import GitPilotClient
from selfrepair.gitpilot.planner import build_fix_prompt, build_repair_plan
from selfrepair.healing.failure_classifier import classify_failure
from selfrepair.healing.fix_strategies import apply_fixes
from selfrepair.healing.retry_policy import should_retry
from selfrepair.llm.ollabridge_client import OllaBridgeClient
from selfrepair.matrixlab.verifier import verify_repo
from selfrepair.models import RepoHealthReport
from selfrepair.settings import Settings

logger = logging.getLogger(__name__)


def run_healing_loop(report: RepoHealthReport, repo_dir: Path, settings: Settings) -> RepoHealthReport:
    # Route HuggingFace Spaces through Space-specific healing
    if report.repo.platform == "huggingface" and report.repo.kind == "space":
        return _heal_space(report, repo_dir, settings)

    return _heal_standard(report, repo_dir, settings)


def _heal_space(report: RepoHealthReport, repo_dir: Path, settings: Settings) -> RepoHealthReport:
    """Space-specific healing path using space_healer."""
    from selfrepair.healing.space_healer import heal_space
    from selfrepair.models import SpaceDiagnosisResult

    # Fetch runtime info from HF API if token available
    runtime_info = None
    if settings.hf_token:
        try:
            from huggingface_hub import HfApi
            hf_api = HfApi(token=settings.hf_token)
            info = hf_api.space_info(report.repo.full_name)
            if info.runtime:
                runtime_info = info.runtime.raw
        except Exception as exc:
            logger.warning("Could not fetch Space runtime info: %s", exc)

    diag, changed = heal_space(report, repo_dir, settings, runtime_info)

    report.space_diagnosis = SpaceDiagnosisResult(
        sdk=diag.sdk,
        app_file=diag.app_file,
        hardware=diag.hardware,
        runtime_stage=diag.runtime_stage,
        issues=diag.issues,
        recommendations=diag.recommendations,
        dead_patterns=diag.dead_patterns_found,
        needs_gpu=diag.needs_gpu,
        needs_rebuild=diag.needs_rebuild,
        severity=diag.severity,
        fix_applied=bool(changed),
        fix_explanation="\n".join(report.notes),
    )

    # Handle hardware if needed
    if diag.needs_gpu and settings.hf_token:
        try:
            from selfrepair.inventory.hf_hardware import request_zerogpu
            from huggingface_hub import HfApi
            hf_api = HfApi(token=settings.hf_token)
            namespace = report.repo.namespace or report.repo.full_name.split("/")[0]
            success, hw_report = request_zerogpu(
                hf_api, report.repo.full_name, namespace,
                auto_free=settings.hf_auto_free_zerogpu,
                exclude=settings.hf_zerogpu_exclude_set,
            )
            if success:
                report.notes.append("ZeroGPU assigned")
                if hw_report.freed_slots:
                    report.notes.append(f"Freed slot: {hw_report.freed_slots[0]}")
            else:
                for err in hw_report.errors:
                    report.notes.append(f"Hardware: {err}")
        except Exception as exc:
            logger.warning("Hardware management failed: %s", exc)
            report.notes.append(f"Hardware management failed: {exc}")

    report.finalize_status()
    return report


def _heal_standard(report: RepoHealthReport, repo_dir: Path, settings: Settings) -> RepoHealthReport:
    """Standard healing path for non-Space repositories."""
    gitpilot = GitPilotClient(settings)
    ollabridge = OllaBridgeClient(settings) if settings.ollabridge_enabled else None

    attempt = 0
    while True:
        analyze_repo_layout(report, repo_dir)
        report.repair_plan = build_repair_plan(report)
        verify_repo(report, repo_dir, settings)
        if report.status == "healthy":
            return report

        if not should_retry(attempt, settings.max_fix_attempts):
            report.notes.append(f"max fix attempts reached ({settings.max_fix_attempts})")
            report.finalize_status()
            return report

        report.fix_attempts += 1
        attempt += 1

        # Try LLM-assisted repair via OllaBridge if available
        if ollabridge and ollabridge.available():
            try:
                prompt = build_fix_prompt(report, str(repo_dir))
                suggestion = ollabridge.chat(prompt)
                report.notes.append(f"ollabridge suggestion received ({len(suggestion)} chars)")
            except Exception as exc:
                logger.warning("OllaBridge repair suggestion failed: %s", exc)

        if gitpilot.available():
            gitpilot.run_headless(report.repo.full_name, build_fix_prompt(report, str(repo_dir)), report.branch_name)

        changed = apply_fixes(report, repo_dir)
        report.changed_files = sorted(set(report.changed_files + changed))
        report.notes.append(f"attempt {attempt}: applied {classify_failure(report)} local fixes")
