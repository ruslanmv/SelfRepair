from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from selfrepair.models import RepoRef
from selfrepair.settings import Settings


def sanitize_repo_name(full_name: str) -> str:
    return full_name.replace("/", "__").replace(" ", "-")


class SandboxManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.settings.ensure_directories()

    def clone_repo(self, repo: RepoRef) -> Path:
        destination = self.settings.work_dir / sanitize_repo_name(repo.full_name)
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "clone", "--depth", str(self.settings.clone_depth), repo.clone_url, str(destination)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to clone {repo.full_name}: {result.stderr.strip()}")
        return destination
