"""Issue Watch safety policy.

The hard contract under test:
  * The never-auto-repair set is exactly {security, bug, feature_request, unknown}.
  * Hard escalation patterns (production outage, sev-0, GDPR) win over class.
  * Dependency / CI failure default to REVIEW, not ALLOW (human approval).
"""
from __future__ import annotations

import pytest

pytest.importorskip("selfrepair")
pytest.importorskip("pydantic")

from selfrepair.issues.classifier import (  # noqa: E402
    Classification,
    FailureClass,
)
from selfrepair.issues.policies import (  # noqa: E402
    ISSUE_NEVER_AUTO_REPAIR,
    Repairability,
    decide_repairability,
    derive_priority,
)
from selfrepair.issues.schemas import ExternalIssueDTO  # noqa: E402


def _issue(**kw):
    base = dict(
        provider="github",
        provider_issue_id="1",
        repo_full_name="octo/x",
        number=1,
        title="x",
    )
    base.update(kw)
    return ExternalIssueDTO(**base)


def _classification(cls: FailureClass, confidence: float = 0.9):
    return Classification(cls=cls, confidence=confidence, matched_rule_index=0)


class TestNeverAutoRepairSet:
    def test_set_pinned_to_phase1_contract(self) -> None:
        # If you change this set, you're changing the safety contract; the
        # test fails on purpose so you make the change consciously.
        assert ISSUE_NEVER_AUTO_REPAIR == frozenset(
            {
                FailureClass.SECURITY,
                FailureClass.BUG,
                FailureClass.FEATURE_REQUEST,
                FailureClass.UNKNOWN,
            }
        )


class TestEscalationOverridesEverything:
    @pytest.mark.parametrize(
        "phrase",
        [
            "production outage on merge",
            "GDPR compliance request from customer",
            "P0 — payments broken",
            "customer data leak in logs",
        ],
    )
    def test_escalation_pattern_wins(self, phrase: str) -> None:
        out = decide_repairability(
            _issue(title=phrase),
            _classification(FailureClass.DOCUMENTATION),
        )
        assert out.repairability is Repairability.ESCALATE


class TestNeverAutoRepairClasses:
    @pytest.mark.parametrize(
        "cls",
        [FailureClass.SECURITY, FailureClass.BUG, FailureClass.FEATURE_REQUEST,
         FailureClass.UNKNOWN],
    )
    def test_class_in_never_set_escalates(self, cls: FailureClass) -> None:
        out = decide_repairability(_issue(), _classification(cls))
        assert out.repairability is Repairability.ESCALATE


class TestReviewDefaults:
    def test_dependency_defaults_to_review(self) -> None:
        out = decide_repairability(
            _issue(), _classification(FailureClass.DEPENDENCY)
        )
        assert out.repairability is Repairability.REVIEW

    def test_ci_failure_defaults_to_review(self) -> None:
        out = decide_repairability(
            _issue(), _classification(FailureClass.CI_FAILURE)
        )
        assert out.repairability is Repairability.REVIEW


class TestAllowClasses:
    @pytest.mark.parametrize(
        "cls",
        [FailureClass.DOCUMENTATION, FailureClass.CONFIGURATION, FailureClass.RUNTIME],
    )
    def test_safe_class_allows(self, cls: FailureClass) -> None:
        out = decide_repairability(_issue(), _classification(cls))
        assert out.repairability is Repairability.ALLOW


class TestDerivePriority:
    @pytest.mark.parametrize(
        "labels, expected",
        [
            (("p0",), "critical"),
            (("outage", "bug"), "critical"),
            (("security",), "high"),
            (("security-patch",), "high"),
            (("good-first-issue",), "low"),
            (("documentation",), "low"),
            ((), "medium"),
            (("unrelated-label",), "medium"),
        ],
    )
    def test_priority_table(self, labels: tuple[str, ...], expected: str) -> None:
        assert derive_priority(_issue(labels=labels)) == expected


class TestPolicyDecisionShape:
    def test_to_dict_has_audit_fields(self) -> None:
        out = decide_repairability(
            _issue(), _classification(FailureClass.SECURITY)
        )
        d = out.to_dict()
        assert d["repairability"] == "escalate"
        assert d["class"] == "security"
        assert "reason" in d
