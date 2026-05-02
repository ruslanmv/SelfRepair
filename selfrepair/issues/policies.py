"""Issue Watch safety policy.

Two contracts:

  ISSUE_NEVER_AUTO_REPAIR:
    Classes that are *never* auto-repairable. These issues require human
    triage; the API's run-repair endpoint must reject them with 409.
    Phase-1 set: security, bug, feature_request, unknown. The first three
    have explicit rationale below; `unknown` is the safety default — if
    the classifier couldn't decide, neither should the auto-repair path.

  decide_repairability(issue, classification):
    Returns a Repairability decision for the upsert and UI layers. It
    augments the class-level safety check with content-level signals
    (e.g. body mentions "production outage" — escalate even if the class
    is `documentation`). The runtime semantics are:
      ALLOW    → repairable=True, run-repair endpoint accepts
      REVIEW   → repairable=True, but UI surfaces "approval required"
      ESCALATE → repairable=False, run-repair endpoint rejects (409)

ESCALATE is a hard stop: it propagates into the ORM `repairable` column
and into the policy_decision audit field, so subsequent audits can prove
why a particular issue was never auto-repaired.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from selfrepair.issues.classifier import Classification, FailureClass
from selfrepair.issues.schemas import ExternalIssueDTO


class Repairability(StrEnum):
    ALLOW = "allow"
    REVIEW = "review"
    ESCALATE = "escalate"


# Classes whose default action is "human only". Mutating this set is a
# safety-relevant change; the test in tests/unit/test_issues_policies.py
# pins the values so an accidental shrink during refactor fails CI.
ISSUE_NEVER_AUTO_REPAIR: frozenset[FailureClass] = frozenset(
    {
        FailureClass.SECURITY,
        FailureClass.BUG,
        FailureClass.FEATURE_REQUEST,
        FailureClass.UNKNOWN,
    }
)


# Content patterns that always escalate, regardless of class. These are
# the hard interlocks: "production outage", "compliance request", "PII",
# etc. — never auto-repair even if the title says "fix typo".
_ESCALATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\bproduction\s+outage\b"),
    re.compile(r"(?i)\b(legal|compliance|gdpr|hipaa)\s+(?:request|matter|issue)\b"),
    re.compile(r"(?i)\b(p0|sev[\-\s]?0|sev[\-\s]?1)\b"),
    re.compile(r"(?i)\bcustomer\s+(?:data|pii)\s+(?:leak|exposure|breach)\b"),
)


@dataclass(frozen=True)
class PolicyDecision:
    """Forensic-grade record of why a repairability verdict was reached."""

    repairability: Repairability
    reason: str
    classification: FailureClass

    def to_dict(self) -> dict[str, str]:
        return {
            "repairability": self.repairability.value,
            "reason": self.reason,
            "class": self.classification.value,
        }


def decide_repairability(
    issue: ExternalIssueDTO, classification: Classification
) -> PolicyDecision:
    """Apply safety + class policy to an external issue.

    Order of evaluation (first match wins):
      1. Hard escalation patterns in title|body (production outage, etc.)
      2. Class membership in ISSUE_NEVER_AUTO_REPAIR
      3. Class-specific gates:
         - DEPENDENCY → REVIEW (security-patch deps need human review)
         - CI_FAILURE → REVIEW (CI Guardian owns auto-rerun; we link only)
      4. Default: ALLOW
    """
    text = (issue.title or "") + "\n" + (issue.body_excerpt or "")
    for pattern in _ESCALATE_PATTERNS:
        if pattern.search(text):
            return PolicyDecision(
                repairability=Repairability.ESCALATE,
                reason=f"matched escalation pattern: {pattern.pattern}",
                classification=classification.cls,
            )

    if classification.cls in ISSUE_NEVER_AUTO_REPAIR:
        return PolicyDecision(
            repairability=Repairability.ESCALATE,
            reason=f"class {classification.cls.value} is in never-auto-repair set",
            classification=classification.cls,
        )

    if classification.cls is FailureClass.DEPENDENCY:
        return PolicyDecision(
            repairability=Repairability.REVIEW,
            reason="dependency bumps require human review for breaking changes",
            classification=classification.cls,
        )

    if classification.cls is FailureClass.CI_FAILURE:
        return PolicyDecision(
            repairability=Repairability.REVIEW,
            reason="CI Guardian owns auto-rerun; this surface links only",
            classification=classification.cls,
        )

    return PolicyDecision(
        repairability=Repairability.ALLOW,
        reason=f"class {classification.cls.value} is auto-repair eligible",
        classification=classification.cls,
    )


def derive_priority(issue: ExternalIssueDTO) -> str:
    """Map labels and content to a coarse priority for the UI sort.

    Returns one of: critical / high / medium / low. Lossy by design — the
    UI uses it for ordering only; the audit row carries the labels intact.
    """
    labels = {label.strip().lower() for label in issue.labels}
    if labels & {"p0", "sev-0", "sev0", "critical", "outage"}:
        return "critical"
    if labels & {
        "p1", "sev-1", "sev1", "high", "security", "security-patch", "blocker",
    }:
        return "high"
    if labels & {"p3", "p4", "low", "documentation", "good-first-issue"}:
        return "low"
    # Default to medium so we don't quietly bury an unlabelled-but-real bug.
    return "medium"
