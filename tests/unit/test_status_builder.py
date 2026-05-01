from selfrepair.models import RepoHealthReport
from selfrepair.reporting.status_builder import build_summary

def test_build_summary(sample_repo):
    report = RepoHealthReport(repo=sample_repo, status="healthy")
    summary = build_summary("Title", "Desc", [report])
    assert summary.healthy == 1
