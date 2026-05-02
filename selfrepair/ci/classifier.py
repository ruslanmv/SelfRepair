"""Deterministic-first failure classification for CI logs.

Per ADR-0001 the rules come first; LLM is only ever a fallback. Every
class maps to a default policy action in `selfrepair.ci.policies`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class FailureClass(StrEnum):
    TRANSIENT_INFRA = "transient_infra"
    RUNNER_CAPACITY = "runner_capacity"
    FLAKY_TEST = "flaky_test"
    TEST_FAILURE = "test_failure"
    LINT_FAILURE = "lint_failure"
    TYPECHECK_FAILURE = "typecheck_failure"
    WORKFLOW_CONFIG = "workflow_config"
    MISSING_DEPENDENCY = "missing_dependency"
    DEPENDENCY_RESOLUTION = "dependency_resolution"
    PERMISSION_ERROR = "permission_error"
    SECRET_OR_ENV_MISSING = "secret_or_env_missing"
    SECURITY_SCAN_FAILURE = "security_scan_failure"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class _Rule:
    cls: FailureClass
    pattern: re.Pattern[str]
    confidence: float


# Order matters: first match wins. Specific patterns first.
_RULES: list[_Rule] = [
    # ---- safety-critical (must beat the generic rules) ----
    _Rule(
        FailureClass.PERMISSION_ERROR,
        re.compile(r"(?i)Resource not accessible by integration"),
        0.95,
    ),
    _Rule(
        FailureClass.PERMISSION_ERROR,
        re.compile(r"(?i)permission denied|access denied|forbidden"),
        0.85,
    ),
    _Rule(
        FailureClass.SECRET_OR_ENV_MISSING,
        re.compile(r"(?i)secret\s+\S+\s+not\s+found"),
        0.95,
    ),
    _Rule(
        FailureClass.SECRET_OR_ENV_MISSING,
        re.compile(
            r"(?i)environment\s+variable\s+\S+\s+(?:not\s+set|missing)"
        ),
        0.9,
    ),
    _Rule(
        FailureClass.SECRET_OR_ENV_MISSING,
        re.compile(r"AWS_ACCESS_KEY_ID\s*(?:is\s*)?(?:not\s*set|missing)"),
        0.9,
    ),
    _Rule(
        FailureClass.SECURITY_SCAN_FAILURE,
        re.compile(
            r"(?i)trivy:\s*scan\s+failed|gitleaks:\s*found\s+\d+\s+leaks"
        ),
        0.95,
    ),
    # ---- workflow YAML problems ----
    _Rule(
        FailureClass.WORKFLOW_CONFIG,
        re.compile(
            r"(?i)Invalid workflow file|YAMLException|workflow is not valid"
        ),
        0.9,
    ),
    # ---- runner capacity ----
    _Rule(
        FailureClass.RUNNER_CAPACITY,
        re.compile(
            r"(?i)No space left on device|out of disk|out of memory"
        ),
        0.9,
    ),
    _Rule(
        FailureClass.RUNNER_CAPACITY,
        re.compile(r"(?i)hosted runner.*not available|no runners available"),
        0.85,
    ),
    # ---- transient infra ----
    _Rule(
        FailureClass.TRANSIENT_INFRA,
        re.compile(r"\b(?:HTTP)?\s*(?:429|502|503|504)\b"),
        0.85,
    ),
    _Rule(
        FailureClass.TRANSIENT_INFRA,
        re.compile(
            r"(?i)ECONNRESET|ECONNREFUSED|ETIMEDOUT|TLS handshake timeout"
        ),
        0.9,
    ),
    _Rule(
        FailureClass.TRANSIENT_INFRA,
        re.compile(r"(?i)temporary failure in name resolution"),
        0.9,
    ),
    # ---- dependency-class ----
    _Rule(
        FailureClass.DEPENDENCY_RESOLUTION,
        re.compile(
            r"(?i)Could not find a version that satisfies|"
            r"version resolution impossible|conflicting dependencies"
        ),
        0.9,
    ),
    _Rule(
        FailureClass.MISSING_DEPENDENCY,
        re.compile(r"ModuleNotFoundError:|ImportError: No module named"),
        0.9,
    ),
    _Rule(
        FailureClass.MISSING_DEPENDENCY,
        re.compile(r"Cannot find module"),
        0.85,
    ),
    _Rule(
        FailureClass.MISSING_DEPENDENCY,
        re.compile(r"go: module .+ not found|go: cannot find package"),
        0.9,
    ),
    # ---- typecheck ----
    _Rule(
        FailureClass.TYPECHECK_FAILURE,
        re.compile(
            r"(?:^|\n)\S+:\d+:\d+:\s*error:.*\[(?:assignment|arg-type|return-value)\]"
        ),
        0.85,
    ),
    _Rule(
        FailureClass.TYPECHECK_FAILURE,
        re.compile(r"\bmypy\b.*Found \d+ error"),
        0.85,
    ),
    _Rule(
        FailureClass.TYPECHECK_FAILURE,
        re.compile(r"error TS\d+:"),
        0.85,
    ),
    # ---- lint ----
    _Rule(
        FailureClass.LINT_FAILURE,
        re.compile(
            r"\b(?:ruff|eslint|prettier|black)\b.*(?:would reformat|error)"
        ),
        0.85,
    ),
    _Rule(
        FailureClass.LINT_FAILURE,
        re.compile(r"\b[EFW]\d{3}\b"),
        0.7,
    ),
    # ---- tests (last; pytest output overlaps with lots of stuff) ----
    _Rule(
        FailureClass.TEST_FAILURE,
        re.compile(r"FAILED\s+\S+::\S+|AssertionError"),
        0.8,
    ),
    _Rule(
        FailureClass.TEST_FAILURE,
        re.compile(r"\b\d+\s+failed,\s+\d+\s+passed"),
        0.9,
    ),
    # ---- flake markers ----
    _Rule(
        FailureClass.FLAKY_TEST,
        re.compile(r"(?i)flaky|retry attempt \d+|reran successfully"),
        0.7,
    ),
]


@dataclass(frozen=True)
class Classification:
    cls: FailureClass
    confidence: float
    error_signature: str
    matched_rule_index: int


def classify_failure(redacted_log: str) -> Classification:
    """Return the first matching rule's class.

    `redacted_log` MUST already be redacted (selfrepair.ci.redaction).
    Returns UNKNOWN with confidence 0.0 if no rule matches.
    """
    if not redacted_log:
        return Classification(
            cls=FailureClass.UNKNOWN,
            confidence=0.0,
            error_signature="",
            matched_rule_index=-1,
        )

    for i, rule in enumerate(_RULES):
        match = rule.pattern.search(redacted_log)
        if match:
            return Classification(
                cls=rule.cls,
                confidence=rule.confidence,
                error_signature=match.group(0)[:200],
                matched_rule_index=i,
            )
    return Classification(
        cls=FailureClass.UNKNOWN,
        confidence=0.0,
        error_signature="",
        matched_rule_index=-1,
    )
