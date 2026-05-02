from __future__ import annotations

from selfrepair.main import run_daily


def test_run_daily_no_github(monkeypatch, temp_settings):
    class FakeDiscovery:
        def __init__(self, settings):
            pass

        def list_repositories(self):
            return []

    monkeypatch.setattr("selfrepair.main.GitHubOrgDiscovery", FakeDiscovery)
    monkeypatch.setattr("selfrepair.main.GitLabDiscovery", FakeDiscovery)
    reports = run_daily(temp_settings)
    assert reports == []
