"""Smoke test for the Issue Watch ORM additions in migration 0003.

Doesn't talk to a real database — inspects metadata and the
ExternalIssueActionType enum. Real CRUD tests live in integration
tests gated on a Postgres fixture.
"""
from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")

from selfrepair.persistence import Base, models  # noqa: E402,F401
from selfrepair.persistence.models import (  # noqa: E402
    ExternalIssue,
    ExternalIssueAction,
    ExternalIssueActionType,
    JobTrigger,
)


class TestIssueWatchMetadata:
    def test_two_new_tables_registered(self) -> None:
        for name in ("external_issue", "external_issue_action"):
            assert name in Base.metadata.tables, f"{name} not registered"

    def test_external_issue_unique_per_provider_id(self) -> None:
        names = {c.name for c in ExternalIssue.__table__.constraints if c.name}
        assert "uq_external_issue_provider_id" in names

    def test_external_issue_dashboard_index(self) -> None:
        names = {idx.name for idx in ExternalIssue.__table__.indexes}
        # The Open Issues table queries by repo + state + recency
        assert "ix_external_issue_dashboard" in names

    def test_action_links_back_to_pipeline(self) -> None:
        """run_repair must thread back into the existing job/finding/repair."""
        fks = {fk.target_fullname for fk in ExternalIssueAction.__table__.foreign_keys}
        assert "job.id" in fks
        assert "finding.id" in fks
        assert "repair.id" in fks
        assert "external_issue.id" in fks

    def test_action_status_default_is_pending(self) -> None:
        col = ExternalIssueAction.__table__.columns["action_status"]
        assert col.default is not None
        # SqlAlchemy stores defaults as ColumnDefault objects; the value is
        # the string that ends up in the row.
        assert col.default.arg == "pending"


class TestExternalIssueActionTypeEnum:
    def test_all_eight_actions_present(self) -> None:
        expected = {
            "sync",
            "triage",
            "create_finding",
            "run_repair",
            "comment",
            "suppress",
            "link_existing_repair",
            "close_external_issue",
        }
        actual = {member.value for member in ExternalIssueActionType}
        assert actual == expected

    def test_action_orm_enum_uses_lowercase_values(self) -> None:
        col = ExternalIssueAction.__table__.columns["action_type"]
        orm_values = set(col.type.enums)
        python_values = {member.value for member in ExternalIssueActionType}
        assert python_values == orm_values


class TestJobTriggerExtension:
    def test_issue_trigger_is_additive(self) -> None:
        """The original triggers + the CI Guardian additions must still be
        present; ISSUE is added alongside them, never in place of."""
        original = {"scheduled", "webhook", "manual", "retry"}
        ci_guardian = {"ci_failure", "ci_verification"}
        new = {"issue"}
        actual = {member.value for member in JobTrigger}
        assert original.issubset(actual), "original triggers were removed"
        assert ci_guardian.issubset(actual), "CI Guardian triggers were removed"
        assert new.issubset(actual), "issue trigger missing"
