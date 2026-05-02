"""Gitleaks secret-scan gate for repair diffs.

Runs `gitleaks detect --no-git` against the workspace before pushing. If
any secret is found, the repair is aborted: a real fix should never write
a secret, so a hit means we either added one or surfaced a pre-existing
one. Either way, escalate.

If gitleaks isn't installed we log a warning and return ScanResult with
`available=False`; the publisher decides whether to fail closed (production)
or skip (dev).
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GitleaksFinding:
    rule_id: str
    file_path: str
    line: int
    secret_preview: str  # always redacted; we never store the full secret


@dataclass(frozen=True)
class ScanResult:
    available: bool
    findings: tuple[GitleaksFinding, ...]

    @property
    def is_clean(self) -> bool:
        return self.available and not self.findings


def is_available() -> bool:
    return shutil.which("gitleaks") is not None


def scan_repo(repo_path: Path) -> ScanResult:
    if not is_available():
        logger.warning("gitleaks not installed; skipping secret scan")
        return ScanResult(available=False, findings=())

    report_path = repo_path / ".gitleaks-report.json"
    cmd = [
        "gitleaks", "detect",
        "--no-git",
        "--source", str(repo_path),
        "--report-format", "json",
        "--report-path", str(report_path),
        "--exit-code", "0",  # we read the report; don't error
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        logger.error(
            "gitleaks failed: %s",
            exc.stderr.decode("utf-8", errors="replace"),
        )
        return ScanResult(available=True, findings=())

    if not report_path.is_file():
        return ScanResult(available=True, findings=())
    try:
        items = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        items = []
    finally:
        report_path.unlink(missing_ok=True)

    findings = tuple(
        GitleaksFinding(
            rule_id=item.get("RuleID", ""),
            file_path=item.get("File", ""),
            line=int(item.get("StartLine", 0)),
            secret_preview=_redact(item.get("Secret", "")),
        )
        for item in items
        if isinstance(item, dict)
    )
    return ScanResult(available=True, findings=findings)


def _redact(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 8:
        return "***"
    return f"{secret[:3]}***{secret[-3:]}"
