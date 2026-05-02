"""Smoke test for the CI Guardian ORM additions in migration 0002.

Doesn't talk to a real database — inspects metadata and the JobTrigger /
CIFailureStatus enums. Real CRUD tests live in integration tests gated on
a Postgres fixture.
"""
import pytest

pytest.importorskip("sqlalchemy")

from selfrepair.persistence import Base, models  # noqa: E402,F401
from selfrepair.persistence.models import (  # noqa: E402
    CIFailure,
    CIFailureStatus,
    CIWorkflowJob,
    CIWorkflowRun,
    JobTrigger,
)


class TestCIGuardianMetadata:
    def test_three_new_tables_registered(self) -> None:
        for name in ("ci_workflow_run", "ci_workflow_job", "ci_failure"):
            assert name in Base.metadata.tables, f"{name} not registered"

    def test_workflow_run_unique_on_repo_run_attempt(self) -> None:
        names = {c.name for c in CIWorkflowRun.__table__.constraints if c.name}
        assert "uq_ci_run_attempt" in names

    def test_workflow_run_indexes_for_dashboard_and_verifier(self) -> None:
        names = {idx.name for idx in CIWorkflowRun.__table__.indexes}
        # Dashboard query: failing workflows by org
        assert "ix_ci_workflow_run_dashboard" in names
        # Verifier query: "is there a newer green run for this SHA?"
        assert "ix_ci_workflow_run_repo_sha" in names

    def test_workflow_job_unique_on_run_and_github_id(self) -> None:
        names = {c.name for c in CIWorkflowJob.__table__.constraints if c.name}
        assert "uq_ci_workflow_job" in names

    def test_failure_dedup_on_repo_fingerprint(self) -> None:
        names = {c.name for c in CIFailure.__table__.constraints if c.name}
        assert "uq_ci_failure_fingerprint" in names

    def test_failure_carries_safety_columns(self) -> None:
        """Forensic + safety columns surfaced in the design."""
        cols = {c.name for c in CIFailure.__table__.columns}
        for col in (
            "policy_decision",
            "kill_switched",
            "redacted_secret_count",
            "occurrence_count",
            "last_error_signature",
            "diagnostic",
        ):
            assert col in cols, f"{col} missing from ci_failure"

    def test_failure_links_to_existing_pipeline(self) -> None:
        """`repair_job_id` foreign-keys into the existing `job` table.

        Validates the seam from the design: CI Guardian creates a normal
        job (trigger=ci_failure) and links forward to it.
        """
        fks = {fk.target_fullname for fk in CIFailure.__table__.foreign_keys}
        assert "job.id" in fks
        assert "finding.id" in fks
        assert "ci_workflow_run.id" in fks


class TestCIFailureStatusEnum:
    def test_all_eight_states_present(self) -> None:
        expected = {
            "open",
            "rerun_queued",
            "rerun_succeeded",
            "repair_queued",
            "repair_opened",
            "resolved",
            "suppressed",
            "escalated",
        }
        actual = {member.value for member in CIFailureStatus}
        assert actual == expected

    def test_status_orm_enum_matches_python_enum(self) -> None:
        """Migration's ci_failure_status enum must mirror the Python enum."""
        col = CIFailure.__table__.columns["status"]
        orm_values = set(col.type.enums)
        python_values = {member.value for member in CIFailureStatus}
        assert python_values == orm_values


class TestJobTriggerExtension:
    def test_ci_triggers_are_additive(self) -> None:
        """The four original triggers must still exist; two new ones added."""
        original = {"scheduled", "webhook", "manual", "retry"}
        new = {"ci_failure", "ci_verification"}
        actual = {member.value for member in JobTrigger}
        assert original.issubset(actual), "original triggers were removed"
        assert new.issubset(actual), "new CI triggers missing"
