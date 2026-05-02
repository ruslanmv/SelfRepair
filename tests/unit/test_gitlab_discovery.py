from __future__ import annotations

from selfrepair.inventory.gitlab_discovery import GitLabDiscovery
from selfrepair.settings import Settings


def test_gitlab_discovery_no_token(tmp_path):
    settings = Settings(
        WORK_DIR=tmp_path / "work",
        STATE_DIR=tmp_path / "state",
        STATUS_SITE_DIR=tmp_path / "status-site",
    )
    discovery = GitLabDiscovery(settings)
    repos = discovery.list_repositories()
    assert repos == []
