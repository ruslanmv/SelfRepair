"""Smoke test that ORM models build cleanly and cover all expected tables.

Doesn't talk to a real database — just inspects the metadata. Real CRUD tests
live in integration tests gated on a Postgres fixture.
"""
import pytest

pytest.importorskip("sqlalchemy")

from selfrepair.persistence import Base, models  # noqa: E402,F401
from selfrepair.persistence.models import Finding, Job  # noqa: E402
from selfrepair.state.machine import JobState  # noqa: E402


class TestOrmMetadata:
    def test_metadata_includes_all_expected_tables(self) -> None:
        expected = {
            "org", "user_account", "repo", "job", "job_event",
            "finding", "repair", "policy_decision", "provenance", "audit_log",
        }
        actual = set(Base.metadata.tables.keys())
        missing = expected - actual
        assert not missing, f"missing tables: {missing}"

    def test_finding_has_unique_fingerprint_constraint(self) -> None:
        names = {c.name for c in Finding.__table__.constraints if c.name}
        assert "uq_finding_fingerprint" in names

    def test_finding_has_repo_status_index(self) -> None:
        names = {idx.name for idx in Finding.__table__.indexes}
        assert "ix_finding_repo_status" in names

    def test_job_state_enum_covers_all_machine_states(self) -> None:
        state_col = Job.__table__.columns["state"]
        enum_values = set(state_col.type.enums)
        machine_values = {state.value for state in JobState}
        missing = machine_values - enum_values
        assert not missing, f"orm enum missing states: {missing}"

    def test_org_id_is_present_on_all_tenant_tables(self) -> None:
        """Tenancy invariant from ADR-0003."""
        tenant_tables = {
            "user_account", "repo", "job", "finding", "audit_log",
        }
        for name in tenant_tables:
            cols = Base.metadata.tables[name].columns
            assert "org_id" in cols, f"{name} missing org_id"
