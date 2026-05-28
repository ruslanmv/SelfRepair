"""Library-mode in-process API for the SelfRepair v1 client contract.

This is the surface the matrix-maintainer LocalClient calls. Each function
adapts SelfRepair's existing engines (scanners, healing, matrixlab) into the
stable DTOs defined in `selfrepair.api.v1.dtos`.

Where the existing engines need a cloned working tree, we use SandboxManager.
Where they need a Settings object, we fall back to `get_settings()`. Where an
engine signature doesn't fit cleanly, we adapt here rather than refactor the
engine — staying in scope.
"""
from __future__ import annotations

import logging
from typing import Any

from selfrepair.api.v1.dtos import (
    HealthIssueDTO,
    JsonReportDTO,
    RepairResultDTO,
    RepoHealthReportDTO,
    RepoRefDTO,
    ValidationReportDTO,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# adapters from internal models -> v1 DTOs
# ---------------------------------------------------------------------------


def _repo_ref_dto_from_full_name(full_name: str, *, platform: str = "github",
                                 clone_url: str | None = None) -> RepoRefDTO:
    if "/" not in full_name:
        full_name = f"unknown/{full_name}"
    if clone_url is None:
        if platform == "huggingface":
            clone_url = f"https://huggingface.co/{full_name}"
        elif platform == "gitlab":
            clone_url = f"https://gitlab.com/{full_name}.git"
        else:
            clone_url = f"https://github.com/{full_name}.git"
    return RepoRefDTO(
        full_name=full_name,
        clone_url=clone_url,
        platform=platform,  # type: ignore[arg-type]
    )


def _health_status_from_internal(status: str) -> str:
    """Map internal status strings to the DTO Literal."""
    if status in {"healthy", "degraded", "down", "unknown"}:
        return status
    # Internal "repaired" maps to "healthy" for the v1 contract.
    if status == "repaired":
        return "healthy"
    return "unknown"


def _issues_from_internal_report(report: Any, full_name: str) -> list[HealthIssueDTO]:
    """Pull per-check failures and notes into HealthIssueDTOs."""
    issues: list[HealthIssueDTO] = []
    for check in getattr(report, "checks", []) or []:
        ok = bool(getattr(check, "ok", True))
        if ok:
            continue
        issues.append(
            HealthIssueDTO(
                repo=full_name,
                issue_type=str(getattr(check, "name", "check")),
                details=str(getattr(check, "details", "") or ""),
                severity="medium",
            )
        )
    diag = getattr(report, "space_diagnosis", None)
    if diag is not None:
        for problem in getattr(diag, "issues", []) or []:
            issues.append(
                HealthIssueDTO(
                    repo=full_name,
                    issue_type="space_diagnosis",
                    details=str(problem),
                    severity={"critical": "critical", "warning": "medium",
                              "info": "low"}.get(
                        getattr(diag, "severity", "info"), "medium"
                    ),  # type: ignore[arg-type]
                )
            )
    # Fall-back: if status isn't healthy and we have no issues yet, surface notes.
    return issues


# ---------------------------------------------------------------------------
# selfrepair.scanners.scan_repo
# ---------------------------------------------------------------------------


def scan_repo(full_name: str, profile: str | None = None,
              *, platform: str = "github",
              clone_url: str | None = None) -> RepoHealthReportDTO:
    """Scan a repository and return a v1 RepoHealthReportDTO.

    Delegates to the existing analyzer + verifier pipeline. If a working tree
    can't be obtained (network, missing deps), returns an `unknown`-status
    report with a structured note rather than raising.
    """
    repo_dto = _repo_ref_dto_from_full_name(full_name, platform=platform,
                                            clone_url=clone_url)
    metadata: dict[str, Any] = {"profile": profile} if profile else {}

    try:
        from selfrepair.analyzers.repo_analyzer import analyze_repo_layout
        from selfrepair.matrixlab.sandbox import SandboxManager
        from selfrepair.matrixlab.verifier import verify_repo
        from selfrepair.models import RepoHealthReport, RepoRef
        from selfrepair.settings import get_settings
    except Exception as exc:  # pragma: no cover - import-time guard
        logger.exception("scan_repo: engine imports failed")
        return RepoHealthReportDTO(
            repo=repo_dto, status="unknown",
            notes=[f"engine_unavailable: {exc}"],
            metadata={**metadata, "needs_escalation": True},
        )

    settings = get_settings()
    repo_ref = RepoRef(
        name=full_name.split("/")[-1],
        full_name=full_name,
        clone_url=repo_dto.clone_url,
        default_branch=repo_dto.default_branch,
        platform=repo_dto.platform,  # type: ignore[arg-type]
    )
    report = RepoHealthReport(repo=repo_ref)

    try:
        repo_dir = SandboxManager(settings).clone_repo(repo_ref)
    except Exception as exc:
        logger.warning("scan_repo: clone failed for %s: %s", full_name, exc)
        return RepoHealthReportDTO(
            repo=repo_dto, status="unknown",
            notes=[f"clone_failed: {exc}"],
            metadata={**metadata, "needs_escalation": True},
        )

    try:
        analyze_repo_layout(report, repo_dir)
        verify_repo(report, repo_dir, settings)
    except Exception as exc:
        logger.exception("scan_repo: analyze/verify failed")
        report.notes.append(f"scan_error: {exc}")
        report.finalize_status()

    issues = _issues_from_internal_report(report, full_name)
    return RepoHealthReportDTO(
        repo=repo_dto,
        generated_at=getattr(report, "generated_at", None) or
                     RepoHealthReportDTO.model_fields["generated_at"].default_factory(),  # type: ignore[misc]
        status=_health_status_from_internal(report.status),  # type: ignore[arg-type]
        issues=issues,
        notes=list(getattr(report, "notes", []) or []),
        metadata={
            **metadata,
            "install_ok": bool(getattr(report, "install_ok", False)),
            "test_ok": bool(getattr(report, "test_ok", False)),
            "start_ok": bool(getattr(report, "start_ok", False)),
            "health_test_ok": bool(getattr(report, "health_test_ok", False)),
        },
    )


# ---------------------------------------------------------------------------
# selfrepair.healing.heal_repo
# ---------------------------------------------------------------------------


def heal_repo(full_name: str, issues: list[dict[str, Any]] | list[Any] | None = None,
              safe_only: bool = True, branch: str | None = None,
              *, platform: str = "github",
              clone_url: str | None = None) -> RepairResultDTO:
    """Run the healing loop against a repo and return a v1 RepairResultDTO.

    The existing `run_healing_loop` operates over an internal RepoHealthReport
    and a working tree; this wrapper bridges the v1 (full_name, issues) shape
    to that engine. `issues` is currently advisory — the engine re-derives its
    own plan from the working tree. We pass it through in `metadata` so the
    matrix-maintainer side can audit what was requested.
    """
    metadata: dict[str, Any] = {
        "requested_issues": [
            i if isinstance(i, dict) else getattr(i, "model_dump", lambda: {})()
            for i in (issues or [])
        ],
        "safe_only": safe_only,
    }
    try:
        from selfrepair.analyzers.repo_analyzer import analyze_repo_layout
        from selfrepair.healing.healing_loop import run_healing_loop
        from selfrepair.matrixlab.sandbox import SandboxManager
        from selfrepair.models import RepoHealthReport, RepoRef
        from selfrepair.settings import get_settings
    except Exception as exc:  # pragma: no cover
        logger.exception("heal_repo: engine imports failed")
        return RepairResultDTO(
            repo=full_name, needs_escalation=True,
            escalation_reason=f"engine_unavailable: {exc}", metadata=metadata,
        )

    settings = get_settings()
    repo_dto = _repo_ref_dto_from_full_name(full_name, platform=platform,
                                            clone_url=clone_url)
    repo_ref = RepoRef(
        name=full_name.split("/")[-1],
        full_name=full_name,
        clone_url=repo_dto.clone_url,
        default_branch=repo_dto.default_branch,
        platform=repo_dto.platform,  # type: ignore[arg-type]
    )
    report = RepoHealthReport(repo=repo_ref, branch_name=branch)

    try:
        repo_dir = SandboxManager(settings).clone_repo(repo_ref)
        analyze_repo_layout(report, repo_dir)
        report = run_healing_loop(report, repo_dir, settings)
    except Exception as exc:
        logger.exception("heal_repo: healing loop failed")
        return RepairResultDTO(
            repo=full_name, needs_escalation=True,
            escalation_reason=f"healing_error: {exc}", metadata=metadata,
        )

    applied = list(getattr(report, "changed_files", []) or [])
    notes = list(getattr(report, "notes", []) or [])
    needs_escalation = report.status not in {"healthy", "repaired"} and bool(applied) is False
    return RepairResultDTO(
        repo=full_name,
        applied=applied,
        skipped=[],
        failed=[],
        changed_files=applied,
        branch=getattr(report, "branch_name", None) or branch,
        needs_escalation=needs_escalation,
        escalation_reason=("status=" + str(report.status)) if needs_escalation else None,
        metadata={**metadata, "notes": notes, "status": str(report.status),
                  "fix_attempts": int(getattr(report, "fix_attempts", 0) or 0)},
    )


# ---------------------------------------------------------------------------
# selfrepair.matrixlab.validate_repo
# ---------------------------------------------------------------------------


def validate_repo(full_name: str, in_sandbox: bool = True,
                  *, platform: str = "github",
                  clone_url: str | None = None) -> ValidationReportDTO:
    """Validate a repo (install/test/start) and return a v1 ValidationReportDTO.

    Delegates to `matrixlab.verifier.verify_repo`. `in_sandbox` selects the
    `sandbox` field on the DTO and (currently) controls whether MatrixLab is
    declared the sandbox; the verifier runs locally under the worker today,
    but the contract surface is stable.
    """
    sandbox_label = "matrixlab" if in_sandbox else "local"
    try:
        from selfrepair.matrixlab.sandbox import SandboxManager
        from selfrepair.matrixlab.verifier import verify_repo as _verify
        from selfrepair.models import RepoHealthReport, RepoRef
        from selfrepair.settings import get_settings
    except Exception as exc:  # pragma: no cover
        logger.exception("validate_repo: engine imports failed")
        return ValidationReportDTO(
            repo=full_name, sandbox="none",
            notes=[f"engine_unavailable: {exc}"],
            metadata={"needs_escalation": True},
        )

    settings = get_settings()
    repo_dto = _repo_ref_dto_from_full_name(full_name, platform=platform,
                                            clone_url=clone_url)
    repo_ref = RepoRef(
        name=full_name.split("/")[-1],
        full_name=full_name,
        clone_url=repo_dto.clone_url,
        default_branch=repo_dto.default_branch,
        platform=repo_dto.platform,  # type: ignore[arg-type]
    )
    report = RepoHealthReport(repo=repo_ref)

    try:
        repo_dir = SandboxManager(settings).clone_repo(repo_ref)
        _verify(report, repo_dir, settings)
    except Exception as exc:
        logger.warning("validate_repo: verify failed for %s: %s", full_name, exc)
        return ValidationReportDTO(
            repo=full_name, sandbox=sandbox_label,  # type: ignore[arg-type]
            notes=[f"validation_error: {exc}"],
            metadata={"needs_escalation": True},
        )

    return ValidationReportDTO(
        repo=full_name,
        install_ok=bool(report.install_ok),
        test_ok=bool(report.test_ok),
        start_ok=bool(report.start_ok),
        health_test_ok=bool(report.health_test_ok),
        sandbox=sandbox_label,  # type: ignore[arg-type]
        notes=list(report.notes or []),
        metadata={},
    )


# ---------------------------------------------------------------------------
# selfrepair.reporting.build_json_report (composed report)
# ---------------------------------------------------------------------------


def build_json_report(full_name: str, *, platform: str = "github",
                      clone_url: str | None = None) -> JsonReportDTO:
    """Build a composite v1 JsonReportDTO: scan + validate, no repair.

    Repair is intentionally NOT triggered here — `report` is read-only by
    contract. Callers wanting a repair must call `selfrepair.repair`
    explicitly.
    """
    health = scan_repo(full_name, platform=platform, clone_url=clone_url)
    validation = validate_repo(full_name, in_sandbox=True, platform=platform,
                               clone_url=clone_url)
    return JsonReportDTO(
        repo=full_name,
        health=health,
        repair=None,
        validation=validation,
        audit={"source": "selfrepair.api.v1.engines.build_json_report"},
    )


__all__ = [
    "build_json_report",
    "heal_repo",
    "scan_repo",
    "validate_repo",
]
