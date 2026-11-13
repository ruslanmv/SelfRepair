"""Migration 0009 creates exactly the tables and columns the ORM models declare, and drops them again."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("alembic")

import sqlalchemy as sa  # noqa: E402
from alembic.migration import MigrationContext  # noqa: E402
from alembic.operations import Operations  # noqa: E402

from selfrepair.agent_repair.models import AgentRepair, AgentRepairEvent  # noqa: E402

MIGRATION = Path(__file__).resolve().parents[3] / "migrations" / "versions" / "0009_agent_repair.py"


def _module():
    spec = importlib.util.spec_from_file_location("m0009", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_chain_is_additive_after_0008():
    m = _module()
    assert m.revision == "0009_agent_repair" and m.down_revision == "0008_service_connections"


def test_upgrade_matches_the_models_and_downgrade_removes_them(tmp_path):
    m = _module()
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            m.upgrade()
        inspector = sa.inspect(conn)
        for model in (AgentRepair, AgentRepairEvent):
            created = {c["name"] for c in inspector.get_columns(model.__tablename__)}
            assert created == {c.name for c in model.__table__.columns}, model.__tablename__
            assert {i["name"] for i in inspector.get_indexes(model.__tablename__)} == {i.name for i in model.__table__.indexes}
        uniques = inspector.get_unique_constraints("agent_repair")
        assert [u["column_names"] for u in uniques] == [["org_id", "attempt_id"]]
        with Operations.context(MigrationContext.configure(conn)):
            m.downgrade()
        assert not {"agent_repair", "agent_repair_event"} & set(sa.inspect(conn).get_table_names())
