from __future__ import annotations

from pathlib import Path

from selfrepair.models import RepoHealthReport, StandardCheck
from selfrepair.standards.python311_rules import ensure_python311
from selfrepair.standards.uv_rules import ensure_uv


def detect_repo_type(repo_dir: Path, platform: str) -> str:
    if platform == "huggingface":
        if (repo_dir / "app.py").exists() or (repo_dir / "requirements.txt").exists():
            return "space"
        if (repo_dir / "dataset_infos.json").exists() or (repo_dir / "data").exists():
            return "dataset"
        return "model"
    if (repo_dir / "package.json").exists():
        return "node"
    if (repo_dir / "pyproject.toml").exists() or (repo_dir / "requirements.txt").exists():
        return "python"
    return "generic"


def analyze_repo_layout(report: RepoHealthReport, repo_dir: Path) -> RepoHealthReport:
    makefile = repo_dir / "Makefile"
    pyproject = repo_dir / "pyproject.toml"
    health_test = repo_dir / "tests" / "test_health.py"
    readme = repo_dir / "README.md"

    report.repo_type = detect_repo_type(repo_dir, report.repo.platform)
    report.makefile_ok = makefile.exists()
    report.pyproject_ok = pyproject.exists()
    report.health_test_ok = health_test.exists()
    report.python311_ok = ensure_python311(pyproject) if pyproject.exists() else False
    report.uv_ok = ensure_uv(pyproject) if pyproject.exists() else False
    report.metadata_ok = readme.exists()

    report.checks = [
        StandardCheck(name="makefile", ok=report.makefile_ok),
        StandardCheck(name="pyproject", ok=report.pyproject_ok),
        StandardCheck(name="health_test", ok=report.health_test_ok),
        StandardCheck(name="python311", ok=report.python311_ok),
        StandardCheck(name="uv", ok=report.uv_ok),
        StandardCheck(name="readme", ok=report.metadata_ok),
    ]

    # HuggingFace Space-specific checks. analyze_space appends to report.checks
    # in place; we don't need its return value here.
    if report.repo.platform == "huggingface" and report.repo_type == "space":
        from selfrepair.analyzers.space_analyzer import analyze_space
        analyze_space(report, repo_dir)

    return report
