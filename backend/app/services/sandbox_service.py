from __future__ import annotations

from pathlib import Path

from selfrepair.matrixlab.sandbox import SandboxManager, sanitize_repo_name
from selfrepair.models import RepoRef
from selfrepair.settings import Settings


class SandboxService:
    """Creates isolated working directories for safe repository execution."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.manager = SandboxManager(settings)

    def clone(self, repo: RepoRef) -> Path:
        return self.manager.clone_repo(repo)

    def expected_workspace(self, repo: RepoRef) -> Path:
        return self.settings.work_dir / sanitize_repo_name(repo.full_name)
