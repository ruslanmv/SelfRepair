from __future__ import annotations

from selfrepair.matrixlab.executor import execute_command


def run_install(repo_dir, timeout_seconds):
    return execute_command(repo_dir, ["make", "install"], timeout_seconds)
