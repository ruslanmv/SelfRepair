"""Scanner sidecar runner and plugin descriptors.

Per ADR-0004 scanners are containers, not Python imports. Adding a scanner
means shipping an image with a `plugin.yaml` manifest — no Python changes
required in this repository.

This module also re-exports `scan_repo`, the library-mode entry point for the
v1 client contract (see `selfrepair.api.v1`). It is a thin wrapper around the
existing scan engine and produces a `RepoHealthReportDTO`.
"""
from selfrepair.api.v1.engines import scan_repo
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
    "scan_repo",
]
