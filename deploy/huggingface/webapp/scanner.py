"""Bridge between the web UI and RepoGuardian core engine."""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone

from .database import AuditLog, RepoReport, ScanRun, SessionLocal

logger = logging.getLogger(__name__)


def _run_scan_background(scan_id: str, user_id: str, settings_override: dict) -> None:
    """Run a RepoGuardian scan in a background thread."""
    db = SessionLocal()
    try:
        scan = db.query(ScanRun).filter_by(id=scan_id).first()
        if not scan:
            return

        # Import RepoGuardian core
        from selfrepair.settings import Settings
        from selfrepair.main import run_daily

        # Build settings from user overrides
        import os
        env_overrides = {}
        if settings_override.get("github_token"):
            env_overrides["GITHUB_TOKEN"] = settings_override["github_token"]
        if settings_override.get("github_org"):
            env_overrides["GITHUB_ORG"] = settings_override["github_org"]
        if settings_override.get("github_user"):
            env_overrides["GITHUB_USER"] = settings_override["github_user"]
        if settings_override.get("gitlab_token"):
            env_overrides["GITLAB_TOKEN"] = settings_override["gitlab_token"]
        if settings_override.get("hf_token"):
            env_overrides["HF_TOKEN"] = settings_override["hf_token"]
        if settings_override.get("hf_namespace"):
            env_overrides["HF_NAMESPACE"] = settings_override["hf_namespace"]

        # Set env vars temporarily
        old_env = {}
        for k, v in env_overrides.items():
            old_env[k] = os.environ.get(k)
            os.environ[k] = v

        try:
            # Force DRY_RUN in HF Spaces for safety
            os.environ["DRY_RUN"] = "true"
            os.environ["WORK_DIR"] = "/tmp/repoguardian/work"
            os.environ["STATE_DIR"] = "/tmp/repoguardian/state"
            os.environ["STATUS_SITE_DIR"] = "/tmp/repoguardian/status-site"

            settings = Settings()
            settings.ensure_directories()

            start_time = time.time()
            reports = run_daily(settings)

            # Store results
            healthy = degraded = down = repaired = 0
            for report in (reports or []):
                repo_report = RepoReport(
                    scan_id=scan_id,
                    repo_name=report.repo.full_name,
                    platform=report.platform or "github",
                    kind=report.repo.kind,
                    status=report.status,
                    makefile_ok=report.makefile_ok,
                    pyproject_ok=report.pyproject_ok,
                    health_test_ok=report.health_test_ok,
                    python311_ok=report.python311_ok,
                    install_ok=report.install_ok,
                    test_ok=report.test_ok,
                    start_ok=report.start_ok,
                    fix_attempts=report.fix_attempts,
                    changed_files=", ".join(report.changed_files),
                    notes="; ".join(report.notes),
                    pr_url=report.pr_url,
                    duration_seconds=time.time() - start_time,
                )
                db.add(repo_report)

                if report.status == "healthy":
                    healthy += 1
                elif report.status == "degraded":
                    degraded += 1
                elif report.status == "down":
                    down += 1
                elif report.status == "repaired":
                    repaired += 1

            scan.status = "completed"
            scan.finished_at = datetime.now(timezone.utc)
            scan.total_repos = len(reports or [])
            scan.healthy = healthy
            scan.degraded = degraded
            scan.down = down
            scan.repaired = repaired
            scan.report_json = json.dumps(
                [r.model_dump(mode="json") for r in (reports or [])],
                default=str,
            )
            db.commit()

        finally:
            # Restore env
            for k, v in old_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    except Exception as e:
        logger.exception("Scan %s failed: %s", scan_id, e)
        scan = db.query(ScanRun).filter_by(id=scan_id).first()
        if scan:
            scan.status = "failed"
            scan.finished_at = datetime.now(timezone.utc)
            scan.report_json = json.dumps({"error": str(e)})
            db.commit()
    finally:
        db.close()


def start_scan(user_id: str, settings_override: dict) -> str:
    """Start a new scan run and return the scan ID."""
    db = SessionLocal()
    try:
        scan = ScanRun(user_id=user_id, trigger="manual")
        db.add(scan)

        audit = AuditLog(
            user_id=user_id,
            action="scan_started",
            details=f"Manual scan triggered",
        )
        db.add(audit)
        db.commit()
        scan_id = scan.id

        # Launch background thread
        thread = threading.Thread(
            target=_run_scan_background,
            args=(scan_id, user_id, settings_override),
            daemon=True,
        )
        thread.start()

        return scan_id
    finally:
        db.close()


def get_scan_status(scan_id: str) -> dict | None:
    """Get current status of a scan run."""
    db = SessionLocal()
    try:
        scan = db.query(ScanRun).filter_by(id=scan_id).first()
        if not scan:
            return None
        return {
            "id": scan.id,
            "status": scan.status,
            "started_at": scan.started_at.isoformat() if scan.started_at else None,
            "finished_at": scan.finished_at.isoformat() if scan.finished_at else None,
            "total_repos": scan.total_repos,
            "healthy": scan.healthy,
            "degraded": scan.degraded,
            "down": scan.down,
            "repaired": scan.repaired,
        }
    finally:
        db.close()
