"""`alembic upgrade head` on a real PostgreSQL, then `SqlReviewStore` round trips.

Skipped unless `SELFREPAIR_TEST_DATABASE_URL` points at a server where the
user may create databases, for example:

    SELFREPAIR_TEST_DATABASE_URL=postgresql+psycopg://postgres@localhost:5432/postgres

The test creates and drops its own throwaway database. It never migrates the
database named in the URL.
"""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytest.importorskip("alembic")
pytest.importorskip("asyncpg")
pytest.importorskip("psycopg")

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from selfrepair.reviewer.schemas import FindingRecord, RunRecord  # noqa: E402
from selfrepair.reviewer.store import SqlReviewStore  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SERVER_URL = os.getenv("SELFREPAIR_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not SERVER_URL, reason="SELFREPAIR_TEST_DATABASE_URL is not set"
)


@pytest.fixture()
def migrated_url(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    server = make_url(str(SERVER_URL)).set(drivername="postgresql+psycopg")
    name = f"selfrepair_review_{uuid.uuid4().hex[:10]}"
    admin = create_engine(server, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = server.set(database=name)
    sync_url = url.render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", sync_url)
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    try:
        command.upgrade(cfg, "head")
        yield url
        # The migration also has to come back down cleanly.
        command.downgrade(cfg, "0006_routines")
        command.upgrade(cfg, "head")
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _seed(url, org_id: uuid.UUID, repo_id: uuid.UUID, installation: int) -> None:  # noqa: ANN001
    engine = create_engine(url)
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO org (id, name, plan, created_at) VALUES (:id, :name, 'free', now())"),
            {"id": org_id, "name": f"org-{org_id.hex[:8]}"},
        )
        conn.execute(
            text(
                "INSERT INTO repo (id, org_id, provider, full_name, default_branch, "
                "config_yaml, github_installation_id) VALUES "
                "(:id, :org, 'github', 'octo/demo', 'main', :cfg, :inst)"
            ),
            {
                "id": repo_id,
                "org": org_id,
                "cfg": "version: 1\nreviewer:\n  enabled: true\n",
                "inst": installation,
            },
        )
    engine.dispose()


async def test_upgrade_head_then_round_trip_through_sql_store(migrated_url) -> None:  # noqa: ANN001
    sync_url = migrated_url.render_as_string(hide_password=False)
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    repo_a, repo_b = uuid.uuid4(), uuid.uuid4()
    _seed(sync_url, org_a, repo_a, 11)
    _seed(sync_url, org_b, repo_b, 22)

    async_url = migrated_url.set(drivername="postgresql+asyncpg")
    engine = create_async_engine(async_url)
    store = SqlReviewStore(async_sessionmaker(engine, expire_on_commit=False))
    try:
        # Same full_name in two orgs: installation id disambiguates, none is ambiguous.
        resolved = await store.resolve_repo(
            provider="github", full_name="octo/demo", installation_id=11
        )
        assert resolved is not None and resolved.repo_id == repo_a and not resolved.ambiguous
        ambiguous = await store.resolve_repo(
            provider="github", full_name="octo/demo", installation_id=None
        )
        assert ambiguous is not None and ambiguous.ambiguous

        assert await store.claim_delivery(provider="github", delivery_id="d1") is True
        assert await store.claim_delivery(provider="github", delivery_id="d1") is False

        run = RunRecord(
            id=uuid.uuid4(),
            org_id=org_a,
            repo_id=repo_a,
            provider="github",
            event_type="push",
            delivery_id="d1",
            ref="refs/heads/main",
            base_sha="a" * 40,
            head_sha="b" * 40,
            engine="deterministic",
            policy_version="1",
            status="running",
            commit_shas=["b" * 40],
            metadata={"repo_full_name": "octo/demo", "branch": "main"},
            started_at=datetime.now(UTC),
        )
        inserted = await store.insert_run(run)
        assert inserted.id == run.id
        again = await store.insert_run(run.model_copy(update={"id": uuid.uuid4()}))
        assert again.id == run.id  # change-set identity is unique

        read = await store.get_run(run.id)
        assert read is not None
        assert read.head_sha == "b" * 40
        assert read.commit_shas == ["b" * 40]
        assert read.metadata["repo_full_name"] == "octo/demo"

        finding = FindingRecord(
            fingerprint="f" * 64,
            category="security",
            severity="high",
            file_path="app.py",
            start_line=2,
            title="eval",
            description="eval of input",
            source="deterministic",
        )
        await store.add_findings(run.id, [finding, finding])
        assert [item.fingerprint for item in await store.list_findings(run.id)] == ["f" * 64]

        await store.add_publication(
            org_id=org_a,
            run_id=run.id,
            provider="github",
            kind="check",
            status="published",
            external_id="123",
            fingerprints=["f" * 64],
            payload={"name": "SelfRepair / Review"},
        )

        newer = run.model_copy(update={"id": uuid.uuid4(), "head_sha": "c" * 40})
        await store.insert_run(newer)
        assert await store.supersede_ref(
            repo_id=repo_a, ref="refs/heads/main", except_run_id=newer.id
        ) == 1
        old = await store.get_run(run.id)
        assert old is not None and old.status == "superseded" and old.conclusion == "cancelled"

        updated = await store.update_run(
            newer.id,
            status="completed",
            conclusion="success",
            metadata={"repo_full_name": "octo/demo", "remediations": [{"id": "t1"}]},
        )
        assert updated.metadata["remediations"] == [{"id": "t1"}]

        assert {item.id for item in await store.list_runs(org_id=org_a)} == {run.id, newer.id}
        assert await store.list_runs(org_id=org_b) == []

        await store.put_settings(org_id=org_a, repo_id=None, config={"enabled": True})
        await store.put_settings(org_id=org_a, repo_id=None, config={"enabled": False})
        org_cfg, _ = await store.settings_for(org_id=org_a, repo_id=repo_a)
        assert org_cfg == {"enabled": False}
    finally:
        await engine.dispose()

    # The partial unique index allows one org default per org.
    sync = create_engine(sync_url)
    with pytest.raises(IntegrityError), sync.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO review_settings (id, org_id, repo_id, config, updated_at) "
                "VALUES (:id, :org, NULL, '{}'::jsonb, now())"
            ),
            {"id": uuid.uuid4(), "org": org_a},
        )
    sync.dispose()
