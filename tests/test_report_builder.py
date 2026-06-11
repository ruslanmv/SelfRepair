"""Offline tests for the report builder."""
from __future__ import annotations

import json
from pathlib import Path

from selfrepair.coders.gitpilot_client import RepairResponse
from selfrepair.planning.repair_plan import build_repair_plan
from selfrepair.reporting.report_builder import build_reports
from selfrepair.validation.matrixlab_client import RunResult


def _sample_plan(repo_url: str = "https://example.com/repo.git"):
    issues = [
        {
            "id": "missing-license",
            "severity": "medium",
            "description": "No LICENSE.",
            "recommended_action": "Add a LICENSE.",
        }
    ]
    return build_repair_plan(
        repo_url=repo_url,
        issues=issues,
        client_id="agent-matrix",
        workspace_id="ws-1",
        branch="main",
    )


def test_build_reports_writes_all_formats(tmp_path: Path) -> None:
    plan = _sample_plan()
    repair = RepairResponse(
        status="dry_run",
        risk_level="medium",
        changed_files=["LICENSE"],
        stubbed=True,
    )
    validation = RunResult(run_id="run-1", status="passed", exit_code=0, duration_ms=10)

    paths = build_reports(
        plan=plan,
        repair_response=repair,
        validation_result=validation,
        validation_skipped=False,
        output_dir=tmp_path / "reports",
    )

    assert paths["json"].exists()
    assert paths["md"].exists()
    assert paths["html"].exists()

    data = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert data["client_id"] == "agent-matrix"
    assert data["health_score"] == plan.health_score
    assert data["issues"][0]["id"] == "missing-license"
    assert data["repair"]["status"] == "dry_run"
    assert data["validation"]["skipped"] is False
    assert data["validation"]["result"]["status"] == "passed"

    md = paths["md"].read_text(encoding="utf-8")
    assert "Repository Repair Report" in md
    assert "missing-license" in md
    assert "Health score" in md

    html = paths["html"].read_text(encoding="utf-8")
    assert "<html" in html
    assert "missing-license" in html


def test_build_reports_validation_skipped(tmp_path: Path) -> None:
    plan = _sample_plan()
    paths = build_reports(
        plan=plan,
        repair_response=None,
        validation_result=None,
        validation_skipped=True,
        output_dir=tmp_path / "reports",
    )
    data = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert data["validation"]["skipped"] is True
    md = paths["md"].read_text(encoding="utf-8")
    assert "Validation skipped" in md
