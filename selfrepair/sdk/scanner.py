"""Scanner protocol and SARIF helpers.

Most scanners ship as containers and emit SARIF v2.1.0; the worker invokes the
container and parses the output. The in-process `Scanner` protocol exists for
the rare case where a Python-native scanner is appropriate.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from selfrepair.sdk.models import Finding, Severity


@dataclass(frozen=True)
class ScannerResult:
    scanner_id: str
    findings: tuple[Finding, ...]
    raw_output_path: Path | None = None


@runtime_checkable
class Scanner(Protocol):
    """In-process scanners. Most scanners ship as container plugins instead."""

    id: str

    def scan(self, workspace: Path) -> ScannerResult: ...


_SARIF_LEVEL_TO_SEVERITY = {
    "none": Severity.INFO,
    "note": Severity.INFO,
    "warning": Severity.MEDIUM,
    "error": Severity.HIGH,
}


def parse_sarif(sarif_path: Path, scanner_id: str) -> ScannerResult:
    """Parse SARIF v2.1.0 output into Finding records.

    Tolerant of missing optional fields; many scanners emit minimal SARIF.
    """
    payload: dict[str, Any] = json.loads(sarif_path.read_text(encoding="utf-8"))
    findings: list[Finding] = []
    for run in payload.get("runs", []):
        rules = {
            rule.get("id"): rule
            for rule in run.get("tool", {}).get("driver", {}).get("rules", [])
            if rule.get("id")
        }
        for result in run.get("results", []):
            rule_id = result.get("ruleId")
            level = (
                result.get("level")
                or rules.get(rule_id, {}).get("defaultLevel")
                or "warning"
            )
            severity = _SARIF_LEVEL_TO_SEVERITY.get(level, Severity.MEDIUM)

            file_path, line = _extract_location(result)
            cwe = _extract_cwe(rules.get(rule_id, {}))

            findings.append(
                Finding(
                    kind=f"{scanner_id}.{rule_id}" if rule_id else scanner_id,
                    severity=severity,
                    file_path=file_path,
                    line=line,
                    message=(result.get("message") or {}).get("text", ""),
                    rule_id=rule_id,
                    cwe=cwe,
                    snippet=_extract_snippet(result),
                    metadata={"sarif_level": level},
                )
            )
    return ScannerResult(
        scanner_id=scanner_id,
        findings=tuple(findings),
        raw_output_path=sarif_path,
    )


def _extract_location(result: dict[str, Any]) -> tuple[str, int | None]:
    locations = result.get("locations") or []
    if not locations:
        return "", None
    phys = locations[0].get("physicalLocation", {})
    file_path = phys.get("artifactLocation", {}).get("uri", "")
    line = phys.get("region", {}).get("startLine")
    return file_path, line


def _extract_snippet(result: dict[str, Any]) -> str | None:
    locations = result.get("locations") or []
    if not locations:
        return None
    region = locations[0].get("physicalLocation", {}).get("region", {})
    snippet = region.get("snippet", {}).get("text")
    return snippet if isinstance(snippet, str) else None


def _extract_cwe(rule: dict[str, Any]) -> str | None:
    for tag in rule.get("properties", {}).get("tags", []) or []:
        if isinstance(tag, str) and tag.upper().startswith("CWE-"):
            return tag.upper()
    return None
