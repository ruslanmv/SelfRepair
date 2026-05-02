"""Scanner sidecar runner.

Per design §5.3:
  - Worker mounts repo read-only at /in
  - Mounts an empty /out
  - Runs the container per plugin.yaml.runtime
  - Parses the SARIF output via `selfrepair.sdk.parse_sarif`

Network defaults to none. If a plugin needs network (vulnerability DB
updates, Semgrep registry), the manifest opts in via `network: bridge` and
operators are expected to gate egress with an allow-list at the host level.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from selfrepair.scanners.plugin import ScannerPlugin
from selfrepair.sdk.scanner import ScannerResult, parse_sarif

logger = logging.getLogger(__name__)


class DockerNotInstalled(RuntimeError):
    """Raised when docker isn't on PATH and the runner is asked to execute."""


class ScannerTimedOut(RuntimeError):
    """Raised when a scanner exceeds its plugin.yaml timeout."""


@dataclass(frozen=True)
class ScanRunResult:
    plugin_id: str
    sarif_result: ScannerResult
    stdout: str
    stderr: str
    returncode: int


def docker_available() -> bool:
    return shutil.which("docker") is not None


def run_scanner(
    plugin: ScannerPlugin,
    *,
    workspace: Path,
    output_root: Path | None = None,
    docker_bin: str = "docker",
) -> ScanRunResult:
    """Run a scanner plugin against `workspace` and parse its SARIF output."""
    if not docker_available() and docker_bin == "docker":
        raise DockerNotInstalled(
            "docker not on PATH; cannot run scanner sidecar"
        )

    output_root = output_root or Path(
        tempfile.mkdtemp(prefix=f"selfrepair-{plugin.id}-")
    )
    output_root.mkdir(parents=True, exist_ok=True)

    cmd = [
        docker_bin, "run", "--rm",
        "--network", plugin.runtime.network,
        "--cpus", plugin.runtime.cpu,
        "--memory", plugin.runtime.memory,
        "-v", f"{workspace}:/in:ro",
        "-v", f"{output_root}:/out",
        plugin.runtime.image,
        *plugin.runtime.cmd,
    ]
    logger.info("running scanner %s", plugin.id)
    try:
        completed = subprocess.run(
            cmd, capture_output=True, timeout=plugin.runtime.timeout
        )
    except subprocess.TimeoutExpired as exc:
        raise ScannerTimedOut(
            f"scanner {plugin.id} exceeded {plugin.runtime.timeout}s timeout"
        ) from exc

    sarif_path = output_root / "findings.sarif"
    if not sarif_path.is_file():
        logger.warning(
            "scanner %s produced no SARIF; rc=%d stderr=%s",
            plugin.id, completed.returncode,
            completed.stderr.decode("utf-8", errors="replace")[:512],
        )
        sarif_result = ScannerResult(scanner_id=plugin.id, findings=())
    else:
        sarif_result = parse_sarif(sarif_path, scanner_id=plugin.id)

    return ScanRunResult(
        plugin_id=plugin.id,
        sarif_result=sarif_result,
        stdout=completed.stdout.decode("utf-8", errors="replace"),
        stderr=completed.stderr.decode("utf-8", errors="replace"),
        returncode=completed.returncode,
    )
