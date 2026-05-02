"""Deterministic-first classification for external issues.

Mirrors the design philosophy of `selfrepair.ci.classifier`: rules first,
LLM only as a fallback. Classes map onto the same default-action table
the `policies` module enforces, so a class name change here ripples
intentionally into both the safety policy and the UI badge tone.

Inputs are intentionally narrow: title + body + labels. We don't look at
comments — too noisy and too async.

Phase-1 is rule-only. The LLM fallback is wired behind a `classify_with_llm`
seam so it can be swapped in via env without changing call sites.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from selfrepair.issues.schemas import ExternalIssueDTO


class FailureClass(StrEnum):
    """Issue classes used by both the UI and the safety policy.

    Order is significant only in the rule list below; first match wins.
    Names are lower-snake to match the migration enum convention.
    """

    DOCUMENTATION = "documentation"
    DEPENDENCY = "dependency"
    SECURITY = "security"
    CI_FAILURE = "ci_failure"
    RUNTIME = "runtime"
    CONFIGURATION = "configuration"
    BUG = "bug"
    FEATURE_REQUEST = "feature_request"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Classification:
    cls: FailureClass
    confidence: float
    matched_rule_index: int


# ---- label-driven rules ------------------------------------------------
#
# Labels are the most reliable signal: humans pre-classified the issue. We
# match safety-critical labels FIRST so a "security" label always wins over
# a co-existing "bug" label (otherwise "bug" would silently downgrade).

# Set of label names (case-insensitive, hyphen/underscore tolerant) that
# place an issue in a class regardless of title or body content.
_LABEL_RULES: tuple[tuple[FailureClass, frozenset[str]], ...] = (
    (
        FailureClass.SECURITY,
        frozenset(
            {
                "security",
                "vulnerability",
                "cve",
                "credential",
                "secret",
                "exploit",
            }
        ),
    ),
    (
        FailureClass.CI_FAILURE,
        frozenset({"ci", "ci-failure", "build", "build-failure"}),
    ),
    (
        FailureClass.DEPENDENCY,
        frozenset(
            {"dependency", "dependencies", "deps", "renovate", "dependabot"}
        ),
    ),
    (
        FailureClass.DOCUMENTATION,
        frozenset({"documentation", "docs", "readme"}),
    ),
    (
        FailureClass.CONFIGURATION,
        frozenset({"config", "configuration", "settings"}),
    ),
    (
        FailureClass.RUNTIME,
        frozenset({"runtime", "crash", "regression", "panic"}),
    ),
    (
        FailureClass.FEATURE_REQUEST,
        frozenset({"feature", "feature-request", "enhancement", "rfe"}),
    ),
    (
        FailureClass.BUG,
        frozenset({"bug", "defect", "broken"}),
    ),
)


# ---- text rules --------------------------------------------------------
#
# Apply only when no label fired. Patterns search title|body together. The
# safety-critical patterns again come first.

_TEXT_RULES: tuple[tuple[FailureClass, re.Pattern[str], float], ...] = (
    (
        FailureClass.SECURITY,
        re.compile(
            r"(?i)\b(cve-\d{4}-\d+|secret\s+leak|leaked?\s+credential|"
            r"private\s+key|access\s+token|exposed\s+token)\b"
        ),
        0.95,
    ),
    (
        FailureClass.CI_FAILURE,
        re.compile(
            r"(?i)\b(ci\s+(?:fail|failed|broken)|workflow\s+fail|"
            r"github\s+actions\s+fail|pipeline\s+(?:fail|red))\b"
        ),
        0.9,
    ),
    (
        FailureClass.DEPENDENCY,
        re.compile(
            r"(?i)\b(bump\s+\S+\s+to\b|update\s+dependency|outdated\s+"
            r"dependency|vulnerable\s+\S+\s+version)\b"
        ),
        0.85,
    ),
    (
        FailureClass.DOCUMENTATION,
        re.compile(
            r"(?i)\b(readme|documentation|docs?)\b.*\b(out[\s-]?of[\s-]?date|"
            r"outdated|missing|broken\s+link|typo)\b"
        ),
        0.8,
    ),
    (
        FailureClass.RUNTIME,
        re.compile(
            r"(?i)\b(does\s*not\s*start|won'?t\s*start|crash|"
            r"exception\s+at\s+runtime|importerror|modulenotfounderror)\b"
        ),
        0.8,
    ),
    (
        FailureClass.CONFIGURATION,
        re.compile(
            r"(?i)\b(missing\s+config|invalid\s+yaml|env\s+var\s+\S+\s+"
            r"(?:not\s+set|missing))\b"
        ),
        0.8,
    ),
    (
        FailureClass.FEATURE_REQUEST,
        re.compile(
            r"(?i)\b(would\s+(?:be\s+)?(?:nice|love|like)\s+to|"
            r"feature\s+request|add\s+support\s+for|please\s+add)\b"
        ),
        0.7,
    ),
    (
        FailureClass.BUG,
        re.compile(r"(?i)\b(bug|broken|doesn'?t\s+work|incorrect|wrong\s+behaviour)\b"),
        0.65,
    ),
)


def _normalise_label(label: str) -> str:
    return label.strip().lower().replace("_", "-")


def classify_issue(issue: ExternalIssueDTO) -> Classification:
    """Return the best class for this issue.

    Algorithm:
      1. If any label is in a label-rule's set, return that class with high
         confidence (1.0). Safety-critical sets (security, ci) come first.
      2. Otherwise scan title|body with the regex rules; first match wins.
      3. Fallback: UNKNOWN @ 0.0.
    """
    labels = {_normalise_label(label) for label in issue.labels}
    for cls, rule_labels in _LABEL_RULES:
        if labels & rule_labels:
            return Classification(cls=cls, confidence=1.0, matched_rule_index=-1)

    text = (issue.title or "") + "\n" + (issue.body_excerpt or "")
    for index, (cls, pattern, conf) in enumerate(_TEXT_RULES):
        if pattern.search(text):
            return Classification(cls=cls, confidence=conf, matched_rule_index=index)

    return Classification(
        cls=FailureClass.UNKNOWN, confidence=0.0, matched_rule_index=-1
    )
