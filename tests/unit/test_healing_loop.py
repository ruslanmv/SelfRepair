from selfrepair.models import RepoHealthReport
from selfrepair.healing.retry_policy import should_retry

def test_retry_policy():
    assert should_retry(0, 3)
    assert not should_retry(3, 3)

def test_report_finalize(sample_repo):
    report = RepoHealthReport(repo=sample_repo, install_ok=True, test_ok=True, start_ok=True, health_test_ok=True)
    report.finalize_status()
    assert report.status == "healthy"
