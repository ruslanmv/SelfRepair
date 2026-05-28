"""Tests for the v1 stable client contract.

These tests use FastAPI's TestClient and monkeypatch the engine functions so
the suite doesn't require a real git clone or network access.
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from selfrepair.api.v1 import engines as v1_engines
from selfrepair.api.v1.dtos import (
    HealthIssueDTO,
    RepairResultDTO,
    RepoHealthReportDTO,
    RepoRefDTO,
    ValidationReportDTO,
)
from selfrepair.api.v1.rpc import router as v1_router


def _app() -> FastAPI:
    """Build a minimal FastAPI app with only the v1 router mounted.

    Avoids importing the full app factory (which pulls in redis/arq/etc.) for
    a focused unit test.
    """
    app = FastAPI()
    app.include_router(v1_router)
    return app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Default: unauthenticated (env unset)
    monkeypatch.delenv("SELFREPAIR_API_KEY", raising=False)
    return TestClient(_app())


# ---------------------------------------------------------------------------
# /v1/about
# ---------------------------------------------------------------------------


def test_about_shape(client: TestClient) -> None:
    resp = client.get("/v1/about")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "selfrepair"
    assert body["schema_versions"] == ["selfrepair/v1"]
    assert isinstance(body["version"], str) and body["version"]


# ---------------------------------------------------------------------------
# selfrepair.scan
# ---------------------------------------------------------------------------


def _fake_scan(full_name: str, profile: str | None = None, **kw: Any) -> RepoHealthReportDTO:
    return RepoHealthReportDTO(
        repo=RepoRefDTO(full_name=full_name,
                        clone_url=f"https://github.com/{full_name}.git"),
        status="healthy",
        issues=[HealthIssueDTO(repo=full_name, issue_type="noop", severity="low")],
        notes=["fake"],
        metadata={"profile": profile},
    )


def test_scan_returns_valid_dto(client: TestClient,
                                monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v1_engines, "scan_repo", _fake_scan)
    resp = client.post("/v1/rpc", json={
        "jsonrpc": "2.0", "id": 1, "method": "selfrepair.scan",
        "params": {"repo": "octo/hello", "profile": "default"},
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == 1
    assert "error" not in body
    result = body["result"]
    # Validate against the DTO to confirm shape stability.
    parsed = RepoHealthReportDTO.model_validate(result)
    assert parsed.schema_version == "selfrepair/v1"
    assert parsed.repo.full_name == "octo/hello"
    assert parsed.status == "healthy"
    assert parsed.issues[0].schema_version == "selfrepair/v1"


# ---------------------------------------------------------------------------
# JSON-RPC error envelopes
# ---------------------------------------------------------------------------


def test_unknown_method_envelope(client: TestClient) -> None:
    resp = client.post("/v1/rpc", json={
        "jsonrpc": "2.0", "id": 42, "method": "selfrepair.nope", "params": {},
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 42
    assert body["error"]["code"] == -32601
    assert "nope" in body["error"]["message"]


def test_invalid_params_envelope(client: TestClient,
                                 monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v1_engines, "scan_repo", _fake_scan)
    resp = client.post("/v1/rpc", json={
        "jsonrpc": "2.0", "id": 7, "method": "selfrepair.scan",
        "params": {"repo": ""},  # invalid: empty string
    })
    body = resp.json()
    assert body["error"]["code"] == -32602


def test_repair_and_validate_methods(client: TestClient,
                                     monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_heal(full_name: str, **kw: Any) -> RepairResultDTO:
        return RepairResultDTO(repo=full_name, applied=["a.py"],
                               changed_files=["a.py"], branch="fix/x")

    def fake_validate(full_name: str, **kw: Any) -> ValidationReportDTO:
        return ValidationReportDTO(repo=full_name, install_ok=True,
                                   test_ok=True, sandbox="matrixlab")

    monkeypatch.setattr(v1_engines, "heal_repo", fake_heal)
    monkeypatch.setattr(v1_engines, "validate_repo", fake_validate)

    r = client.post("/v1/rpc", json={
        "jsonrpc": "2.0", "id": 1, "method": "selfrepair.repair",
        "params": {"repo": "x/y", "issues": [], "safe_only": True},
    }).json()
    assert r["result"]["branch"] == "fix/x"
    assert r["result"]["schema_version"] == "selfrepair/v1"

    v = client.post("/v1/rpc", json={
        "jsonrpc": "2.0", "id": 2, "method": "selfrepair.validate",
        "params": {"repo": "x/y", "in_sandbox": True},
    }).json()
    assert v["result"]["install_ok"] is True
    assert v["result"]["sandbox"] == "matrixlab"


# ---------------------------------------------------------------------------
# Auth gate
# ---------------------------------------------------------------------------


def test_auth_required_when_key_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SELFREPAIR_API_KEY", "s3cret")
    monkeypatch.setattr(v1_engines, "scan_repo", _fake_scan)
    c = TestClient(_app())

    # missing header -> 401
    resp = c.post("/v1/rpc", json={
        "jsonrpc": "2.0", "id": 1, "method": "selfrepair.scan",
        "params": {"repo": "x/y"},
    })
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == -32600

    # wrong token -> 401
    resp = c.post("/v1/rpc",
                  headers={"Authorization": "Bearer nope"},
                  json={"jsonrpc": "2.0", "id": 1,
                        "method": "selfrepair.scan", "params": {"repo": "x/y"}})
    assert resp.status_code == 401

    # correct token -> 200
    resp = c.post("/v1/rpc",
                  headers={"Authorization": "Bearer s3cret"},
                  json={"jsonrpc": "2.0", "id": 1,
                        "method": "selfrepair.scan", "params": {"repo": "x/y"}})
    assert resp.status_code == 200
    assert resp.json()["result"]["repo"]["full_name"] == "x/y"


def test_auth_open_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SELFREPAIR_API_KEY", raising=False)
    monkeypatch.setattr(v1_engines, "scan_repo", _fake_scan)
    c = TestClient(_app())
    resp = c.post("/v1/rpc", json={
        "jsonrpc": "2.0", "id": 1, "method": "selfrepair.scan",
        "params": {"repo": "x/y"},
    })
    assert resp.status_code == 200
    assert "error" not in resp.json()


# ---------------------------------------------------------------------------
# DTO smoke
# ---------------------------------------------------------------------------


def test_dtos_carry_schema_version() -> None:
    dto = RepoHealthReportDTO(
        repo=RepoRefDTO(full_name="x/y", clone_url="https://example/x/y.git"),
    )
    assert dto.schema_version == "selfrepair/v1"
    assert dto.repo.schema_version == "selfrepair/v1"
