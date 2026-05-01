from __future__ import annotations

from pathlib import Path

from selfrepair.execution.install_runner import run_install
from selfrepair.execution.start_runner import run_start
from selfrepair.execution.test_runner import run_test


class CommandService:
    """Runs install, test, and start commands with bounded timeouts."""

    def run_commands(self, repo_path: str, timeout_seconds: int = 300) -> dict:
        repo_dir = Path(repo_path)
        install = run_install(repo_dir, timeout_seconds)
        test = run_test(repo_dir, timeout_seconds) if install.ok else None
        start = run_start(repo_dir, min(timeout_seconds, 60)) if install.ok and test and test.ok else None
        return {
            "repo_path": str(repo_dir),
            "install": install.model_dump(),
            "test": test.model_dump() if test else None,
            "start": start.model_dump() if start else None,
            "status": "passed" if install.ok and test and test.ok and start and start.ok else "failed",
        }
