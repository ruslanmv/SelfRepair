"""Review conclusions.

The coordinator and the model do not decide whether a finding blocks a merge.
This module does, from the repository's `block_on` list and the validated
findings. Deterministic findings are never dropped in favor of a clean model
report.
"""
from __future__ import annotations

from selfrepair.config.repo_config import ReviewerConfig, _severity_le
from selfrepair.reviewer.schemas import Conclusion, FindingRecord

_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def blocks(config: ReviewerConfig, severity: str) -> bool:
    """Return True when `severity` meets any configured blocking severity."""
    for threshold in config.review.block_on:
        if _RANK.get(severity, 0) >= _RANK.get(threshold, 99):
            return True
    return False


def conclude(
    config: ReviewerConfig,
    findings: list[FindingRecord],
    *,
    incomplete_reason: str | None,
    truncated: bool,
) -> Conclusion:
    """Choose the check conclusion.

    An incomplete engine, a truncated diff, or a transport failure is
    `action_required`. It is never `success`. A clean complete review is
    `success`. Blocking severities fail the check. Informational findings do
    not.
    """
    accepted = [item for item in findings if item.validation_state == "accepted"]
    if any(blocks(config, item.severity) for item in accepted):
        return "failure"
    if incomplete_reason or truncated:
        return "action_required"
    return "success"


def highest(findings: list[FindingRecord]) -> str | None:
    """Return the highest accepted severity, if any."""
    accepted = [item for item in findings if item.validation_state == "accepted"]
    if not accepted:
        return None
    return max(accepted, key=lambda item: _RANK.get(item.severity, 0)).severity


def at_most(severity: str, ceiling: str) -> bool:
    """True when `severity` is at or below `ceiling`. Exposed for tests."""
    return _severity_le(severity, ceiling)
