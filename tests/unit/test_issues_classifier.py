"""Issue classifier rules.

Phase-1 contracts:
  * Labels are the strongest signal — a `security` label always wins.
  * Safety-critical classes (security) beat co-existing weaker labels.
  * Text rules fire only when no label matched.
"""
from __future__ import annotations

import pytest

pytest.importorskip("selfrepair")
pytest.importorskip("pydantic")

from selfrepair.issues.classifier import (  # noqa: E402
    FailureClass,
    classify_issue,
)
from selfrepair.issues.schemas import ExternalIssueDTO  # noqa: E402


def _issue(**kw):
    base = dict(
        provider="github",
        provider_issue_id="1",
        repo_full_name="octo/x",
        number=1,
        title="placeholder",
    )
    base.update(kw)
    return ExternalIssueDTO(**base)


class TestLabelRulesWin:
    def test_security_label_wins_over_bug_label(self) -> None:
        out = classify_issue(_issue(labels=("bug", "security")))
        assert out.cls is FailureClass.SECURITY
        assert out.confidence == 1.0

    def test_dependabot_label_is_dependency(self) -> None:
        out = classify_issue(_issue(labels=("dependabot",)))
        assert out.cls is FailureClass.DEPENDENCY

    def test_documentation_label_is_documentation(self) -> None:
        out = classify_issue(_issue(labels=("docs",)))
        assert out.cls is FailureClass.DOCUMENTATION

    def test_underscore_label_is_normalised(self) -> None:
        out = classify_issue(_issue(labels=("ci_failure",)))
        assert out.cls is FailureClass.CI_FAILURE


class TestTextRulesFireOnlyWithoutLabels:
    def test_cve_in_title_classes_as_security(self) -> None:
        out = classify_issue(_issue(title="Bump go-jose for CVE-2024-28180"))
        assert out.cls is FailureClass.SECURITY

    def test_workflow_failure_text_is_ci_failure(self) -> None:
        out = classify_issue(
            _issue(title="GitHub Actions fail on every PR")
        )
        assert out.cls is FailureClass.CI_FAILURE

    def test_modulenotfounderror_is_runtime(self) -> None:
        out = classify_issue(
            _issue(
                title="Crash on startup",
                body_excerpt="ModuleNotFoundError: no module named 'transformers'",
            )
        )
        assert out.cls is FailureClass.RUNTIME

    def test_would_love_to_is_feature_request(self) -> None:
        out = classify_issue(
            _issue(title="Would love to have JSON output")
        )
        assert out.cls is FailureClass.FEATURE_REQUEST


class TestUnknownFallback:
    def test_unknown_when_nothing_matches(self) -> None:
        out = classify_issue(_issue(title="nothing in particular here"))
        assert out.cls is FailureClass.UNKNOWN
        assert out.confidence == 0.0

    def test_empty_title_is_unknown(self) -> None:
        # Pydantic enforces title>=1, so use minimal input
        out = classify_issue(_issue(title="x"))
        assert out.cls is FailureClass.UNKNOWN
