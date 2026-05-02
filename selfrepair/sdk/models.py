"""Public SDK models. Stable contract for plugin authors."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingStatus(StrEnum):
    OPEN = "open"
    FIXED = "fixed"
    WONT_FIX = "wont_fix"
    SUPPRESSED = "suppressed"


@dataclass(frozen=True)
class Finding:
    """A single detected issue. Stable across runs by `fingerprint`."""

    kind: str
    severity: Severity
    file_path: str
    line: int | None = None
    message: str = ""
    rule_id: str | None = None
    cwe: str | None = None
    cve: str | None = None
    snippet: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        # Excludes line numbers (which drift on unrelated edits) and uses a
        # whitespace-normalized snippet so cosmetic edits don't create dupes.
        normalized_snippet = " ".join((self.snippet or "").split())
        material = "\x00".join(
            [
                self.kind,
                self.rule_id or "",
                self.file_path,
                normalized_snippet,
            ]
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


@dataclass(frozen=True)
class RepoContext:
    """Read-only view of the repository the fixer is acting on."""

    workspace: Path
    full_name: str
    default_branch: str
    primary_language: str | None = None
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RepairPlan:
    """What the fixer intends to do. Reviewed by the policy engine before apply."""

    fixer_id: str
    finding: Finding
    summary: str
    risk: Severity
    files_touched: tuple[str, ...]
    requires_llm: bool = False
    requires_approval: bool = False


@dataclass(frozen=True)
class Patch:
    """A diff produced by a fixer. Applied verbatim under sandbox validation."""

    fixer_id: str
    finding_fingerprint: str
    diff: str  # unified diff format
    files_changed: tuple[str, ...]
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)
