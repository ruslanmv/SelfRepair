"""Public SDK for SelfRepair fixers and scanners.

This is the stable extension surface (ADR-0004). Anything not exported here is
an internal detail and may change without notice.
"""
from selfrepair.sdk.fixer import Fixer, FixerRegistry
from selfrepair.sdk.models import (
    Finding,
    FindingStatus,
    Patch,
    RepairPlan,
    RepoContext,
    Severity,
)
from selfrepair.sdk.scanner import Scanner, ScannerResult, parse_sarif

__all__ = [
    "Finding",
    "FindingStatus",
    "Fixer",
    "FixerRegistry",
    "Patch",
    "RepairPlan",
    "RepoContext",
    "Scanner",
    "ScannerResult",
    "Severity",
    "parse_sarif",
]
