"""Scanner sidecar runner and plugin descriptors.

Per ADR-0004 scanners are containers, not Python imports. Adding a scanner
means shipping an image with a `plugin.yaml` manifest — no Python changes
required in this repository.
"""
from selfrepair.scanners.discovery import discover_scanners
from selfrepair.scanners.plugin import ScannerPlugin, ScannerRuntime, load_plugin
from selfrepair.scanners.runner import (
    DockerNotInstalled,
    ScannerTimedOut,
    ScanRunResult,
    docker_available,
    run_scanner,
)

__all__ = [
    "DockerNotInstalled",
    "ScanRunResult",
    "ScannerPlugin",
    "ScannerRuntime",
    "ScannerTimedOut",
    "discover_scanners",
    "docker_available",
    "load_plugin",
    "run_scanner",
]
