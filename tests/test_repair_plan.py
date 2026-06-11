"""Offline tests for detector-based analysis + repair-plan generation."""
from __future__ import annotations

from pathlib import Path

from selfrepair.analyzers.repo_analyzer import analyze_path
from selfrepair.planning.repair_plan import (
    DEFAULT_FORBIDDEN_PATHS,
    build_repair_plan,
    compute_health_score,
)


def _make_broken_repo(root: Path) -> Path:
    """A repo missing tests/test_health.py, pyproject, LICENSE, workflows."""
    repo = root / "broken"
    repo.mkdir()
    (repo / "README.md").write_text("# Broken\n", encoding="utf-8")
    # Intentionally: no pyproject.toml, no LICENSE, no .github/workflows,
    # no tests/test_health.py, no Makefile.
    return repo


def test_detectors_find_missing_artifacts(tmp_path: Path) -> None:
    repo = _make_broken_repo(tmp_path)
    result = analyze_path(repo)
    ids = {i.id for i in result.issues}
    assert "missing-health-test" in ids
    assert "missing-pyproject" in ids
    assert "missing-license" in ids
    assert "missing-ci-workflow" in ids
    assert "missing-makefile-targets" in ids


def test_health_score_in_range(tmp_path: Path) -> None:
    repo = _make_broken_repo(tmp_path)
    result = analyze_path(repo)
    score = compute_health_score(result.issues)
    assert 0 <= score <= 100
    # A repo missing this much should not be perfectly healthy.
    assert score < 100


def test_plan_json_shape_and_derived_paths(tmp_path: Path) -> None:
    repo = _make_broken_repo(tmp_path)
    result = analyze_path(repo)
    plan = build_repair_plan(
        repo_url=str(repo),
        issues=result,
        client_id="agent-matrix",
        workspace_id="ws-1",
        branch="main",
    )
    data = plan.to_dict()

    # Top-level contract keys.
    for key in (
        "client_id",
        "workspace_id",
        "task_id",
        "repo_url",
        "branch",
        "mode",
        "health_score",
        "issues",
        "allowed_paths",
        "forbidden_paths",
        "coder",
        "sandbox",
    ):
        assert key in data, f"missing key {key}"

    assert data["mode"] == "dry_run"
    assert data["client_id"] == "agent-matrix"
    assert data["coder"] == {"provider": "gitpilot", "model": "code-coder"}
    assert data["sandbox"] == {
        "provider": "matrixlab",
        "profile": "python-repair",
        "required": True,
    }
    assert data["forbidden_paths"] == DEFAULT_FORBIDDEN_PATHS

    # allowed_paths must be DERIVED from the detected issues.
    allowed = set(data["allowed_paths"])
    assert "tests/test_health.py" in allowed
    assert "pyproject.toml" in allowed
    assert "LICENSE" in allowed
    assert ".github/workflows/**" in allowed

    # Each issue carries the contract shape.
    for issue in data["issues"]:
        assert set(issue) == {"id", "severity", "description", "recommended_action"}


def test_client_id_not_hardcoded(tmp_path: Path) -> None:
    repo = _make_broken_repo(tmp_path)
    result = analyze_path(repo)
    plan = build_repair_plan(
        repo_url=str(repo),
        issues=result,
        client_id="some-other-client",
        workspace_id="ws-9",
    )
    assert plan.client_id == "some-other-client"
