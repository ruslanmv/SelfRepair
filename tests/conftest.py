from pathlib import Path

import pytest

from selfrepair.models import RepoRef
from selfrepair.settings import Settings


@pytest.fixture()
def sample_repo() -> RepoRef:
    return RepoRef(name="demo", full_name="agent-matrix/demo", clone_url="https://example.com/demo.git")


@pytest.fixture()
def temp_settings(tmp_path: Path) -> Settings:
    return Settings(
        GITHUB_ORG="agent-matrix",
        WORK_DIR=tmp_path / "work",
        STATE_DIR=tmp_path / "state",
        STATUS_SITE_DIR=tmp_path / "status-site",
        GITPILOT_ENABLED=False,
        MATRIXLAB_ENABLED=False,
    )
