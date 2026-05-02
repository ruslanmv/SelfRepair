from __future__ import annotations

from selfrepair.matrixlab.executor import execute_command


def run_start(repo_dir, timeout_seconds):
    return execute_command(repo_dir, ["make", "start"], timeout_seconds)
