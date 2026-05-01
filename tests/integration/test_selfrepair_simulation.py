from pathlib import Path

from selfrepair.main import check_single_repo
from selfrepair.models import RepoHealthReport, RepoRef, StandardCheck


def test_check_single_repo_simulates_self_repair(monkeypatch, temp_settings):
    repo = RepoRef(
        name="broken-demo",
        full_name="agent-matrix/broken-demo",
        clone_url="https://example.com/broken-demo.git",
    )

    cloned_repo_dir = temp_settings.work_dir / "broken-demo"
    cloned_repo_dir.mkdir(parents=True, exist_ok=True)

    class FakeSandboxManager:
        def __init__(self, settings):
            self.settings = settings

        def clone_repo(self, repo_ref: RepoRef) -> Path:
            assert repo_ref.full_name == "agent-matrix/broken-demo"
            return cloned_repo_dir

    def fake_analyze_repo_layout(report: RepoHealthReport, repo_dir: Path) -> None:
        assert repo_dir == cloned_repo_dir
        report.checks.append(StandardCheck(name="makefile", ok=False, details="missing"))
        report.checks.append(StandardCheck(name="health_test", ok=False, details="missing"))
        report.notes.append("detected_missing_delivery_files")

    def fake_run_healing_loop(report: RepoHealthReport, repo_dir: Path, settings):
        assert repo_dir == cloned_repo_dir
        report.changed_files.extend(["Makefile", "tests/test_health.py"])
        report.install_ok = True
        report.test_ok = True
        report.start_ok = True
        report.health_test_ok = True
        report.notes.append("simulated_self_repair_applied")
        report.finalize_status()
        return report

    def fake_evaluate_policy(changed_files: list[str]) -> dict:
        assert changed_files == ["Makefile", "tests/test_health.py"]
        return {"risk": "low"}

    pushed = {"called": False}

    def fake_push_repair_branch(repo_dir: Path, report: RepoHealthReport, settings) -> None:
        assert repo_dir == cloned_repo_dir
        assert report.status == "healthy"
        assert report.changed_files == ["Makefile", "tests/test_health.py"]
        pushed["called"] = True
        report.pushed_branch = report.branch_name

    monkeypatch.setattr("selfrepair.main.SandboxManager", FakeSandboxManager)
    monkeypatch.setattr("selfrepair.main.analyze_repo_layout", fake_analyze_repo_layout)
    monkeypatch.setattr("selfrepair.main.run_healing_loop", fake_run_healing_loop)
    monkeypatch.setattr("selfrepair.main.evaluate_policy", fake_evaluate_policy)
    monkeypatch.setattr("selfrepair.main.push_repair_branch", fake_push_repair_branch)

    report = check_single_repo(repo, temp_settings)

    assert report.repo.full_name == "agent-matrix/broken-demo"
    assert report.status == "healthy"
    assert report.changed_files == ["Makefile", "tests/test_health.py"]
    assert "detected_missing_delivery_files" in report.notes
    assert "simulated_self_repair_applied" in report.notes
    assert "policy_risk=low" in report.notes
    assert pushed["called"] is True
