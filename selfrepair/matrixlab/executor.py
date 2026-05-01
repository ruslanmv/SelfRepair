from __future__ import annotations

import subprocess
import time
from pathlib import Path

from selfrepair.models import ExecutionResult


def execute_command(repo_dir: Path, command: list[str], timeout_seconds: int) -> ExecutionResult:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return ExecutionResult(
            command=" ".join(command),
            return_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_seconds=time.perf_counter() - started,
        )
    except subprocess.TimeoutExpired as exc:
        return ExecutionResult(
            command=" ".join(command),
            return_code=124,
            stdout=exc.stdout or "",
            stderr=(exc.stderr or "") + "\nTimed out",
            duration_seconds=time.perf_counter() - started,
        )
    except FileNotFoundError as exc:
        return ExecutionResult(
            command=" ".join(command),
            return_code=127,
            stderr=str(exc),
            duration_seconds=time.perf_counter() - started,
        )
