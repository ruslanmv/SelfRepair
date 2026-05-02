from pathlib import Path

import pytest

from selfrepair.models import RepoRef
from selfrepair.settings import Settings


@pytest.fixture(autouse=True)
def isolate_worker_sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Force every test's sandbox under tmp_path.

    Stops stage tests from writing under /var/lib (or the new /tmp default)
    and from leaking artifacts between tests. Production overrides via
    SELFREPAIR_SANDBOX_WORKDIR are unaffected outside the test process.
    """
    monkeypatch.setenv("SELFREPAIR_SANDBOX_WORKDIR", str(tmp_path / "sandbox"))


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
