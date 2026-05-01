from __future__ import annotations

import shutil
import subprocess
from typing import Any

from selfrepair.settings import Settings


class GitPilotClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def available(self) -> bool:
        return self.settings.gitpilot_enabled and shutil.which(self.settings.gitpilot_bin) is not None

    def run_headless(self, repo_name: str, prompt: str, branch_name: str | None = None) -> dict[str, Any]:
        if not self.available():
            return {"success": False, "returncode": None, "stdout": "", "stderr": "gitpilot unavailable"}
        cmd = [self.settings.gitpilot_bin, "run", "--repo", repo_name, "--prompt", prompt]
        if branch_name:
            cmd.extend(["--branch", branch_name])
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return {
            "success": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
