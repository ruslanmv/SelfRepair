"""Deterministic classifier rules for CI log lines.

The phase-1 contract: safety-critical classes (permission, secret, security)
must beat the generic fallbacks. If a permission error is mistaken for a
test failure we end up auto-rerunning a workflow that's broken in a way no
amount of rerun will fix.
"""
from __future__ import annotations

import pytest

pytest.importorskip("selfrepair")

from selfrepair.ci.classifier import (  # noqa: E402
    Classification,
    FailureClass,
    classify_failure,
)


class TestSafetyCriticalRulesWin:
    def test_resource_not_accessible_is_permission_error(self) -> None:
        out = classify_failure(
            "Error: Resource not accessible by integration"
        )
        assert out.cls is FailureClass.PERMISSION_ERROR
        assert out.confidence >= 0.9

    def test_secret_not_found_is_secret_or_env_missing(self) -> None:
        out = classify_failure("secret MY_TOKEN not found")
        assert out.cls is FailureClass.SECRET_OR_ENV_MISSING

    def test_gitleaks_finding_is_security_scan_failure(self) -> None:
        out = classify_failure("gitleaks: found 3 leaks")
        assert out.cls is FailureClass.SECURITY_SCAN_FAILURE


class TestGenericClasses:
    def test_pytest_summary_is_test_failure(self) -> None:
        out = classify_failure("FAILED tests/unit/test_x.py::test_y")
        assert out.cls is FailureClass.TEST_FAILURE

    def test_unknown_when_nothing_matches(self) -> None:
        out = classify_failure("everything is fine")
        assert out.cls is FailureClass.UNKNOWN
        assert out.confidence == 0.0
        assert out.matched_rule_index == -1


class TestSignatureLengthCap:
    def test_signature_truncated_to_200_chars(self) -> None:
        long = "FAILED tests::" + "x" * 1000
        out = classify_failure(long)
        assert isinstance(out, Classification)
        assert len(out.error_signature) <= 200


class TestEmptyInput:
    def test_empty_log_returns_unknown(self) -> None:
        out = classify_failure("")
        assert out.cls is FailureClass.UNKNOWN
        assert out.confidence == 0.0
