"""The Hugging Face Space console API (deploy/huggingface/webapp).

The Space serves the same React console as the full server but has no
worker, Redis, or GitHub App, so review and routine surfaces must answer with
the full API's shapes (empty lists, opt-in defaults, refusals) and never with
fabricated runs.
"""
from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPACE = ROOT / "deploy" / "huggingface"
API = SPACE / "webapp" / "api_v1.py"


def _literal(name: str):
    tree = ast.parse(API.read_text())
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id]
        if name in targets:
            return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found in {API}")


def test_space_reviewer_defaults_match_the_real_config() -> None:
    from selfrepair.config.repo_config import ReviewerConfig

    assert _literal("REVIEWER_DEFAULTS") == ReviewerConfig().model_dump()


def test_space_bundle_matches_its_index() -> None:
    index = (SPACE / "webapp" / "spa" / "index.html").read_text()
    assets = SPACE / "webapp" / "spa" / "assets"
    for name in [p.name for p in assets.iterdir() if p.suffix in {".js", ".css"}]:
        assert f"/assets/{name}" in index, f"{name} is shipped but index.html does not load it"


@pytest.fixture()
def space_client(tmp_path, monkeypatch):
    for module in ("itsdangerous", "multipart", "cryptography", "jinja2", "sqlalchemy"):
        pytest.importorskip(module)
    monkeypatch.setenv("SELFREPAIR_DB_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ADMIN_PASSWORD", "space-test-pass")
    # The Space sets Secure cookies (HTTPS on HF); the test client speaks HTTP.
    monkeypatch.setenv("SELFREPAIR_INSECURE_COOKIES", "1")
    monkeypatch.syspath_prepend(str(SPACE))
    for name in [m for m in sys.modules if m == "webapp" or m.startswith("webapp.")]:
        sys.modules.pop(name)
    try:
        main = importlib.import_module("webapp.main")
    except ImportError as exc:  # optional Space deps (upstash-redis, mailtrap, ...)
        pytest.skip(f"Space dependencies not installed: {exc}")
    from fastapi.testclient import TestClient

    with TestClient(main.app) as client:
        yield client
    for name in [m for m in sys.modules if m == "webapp" or m.startswith("webapp.")]:
        sys.modules.pop(name)


def test_space_review_and_routine_surfaces(space_client) -> None:
    assert space_client.get("/v1/reviews").status_code == 401
    login = space_client.post(
        "/v1/auth/login", json={"username": "admin", "password": "space-test-pass"}
    )
    assert login.status_code == 200, login.text

    assert space_client.get("/v1/reviews").json()["items"] == []
    assert space_client.get("/v1/reviews/abc").status_code == 404
    assert space_client.get("/v1/reviews/abc/findings").status_code == 404
    assert space_client.post("/v1/reviews/abc/retry").status_code == 404
    settings = space_client.get("/v1/review-settings").json()
    assert settings["config"]["enabled"] is False and settings["read_only"] is True
    refused = space_client.put("/v1/review-settings", json={"config": {"enabled": True}})
    assert refused.status_code == 501 and "full SelfRepair server" in refused.json()["detail"]

    assert space_client.get("/v1/routines").json() == {"items": [], "count": 0}
    caps = space_client.get("/v1/routines/capabilities").json()
    assert caps["execution"] != "enabled"
    assert space_client.post("/v1/routines", json={}).status_code == 501

    page = space_client.get("/")
    assert page.status_code == 200 and "/assets/index-" in page.text



def _login_space_admin(client):
    response = client.post(
        "/v1/auth/login",
        json={"username": "admin", "password": "space-test-pass"},
    )
    assert response.status_code == 200, response.text


def test_space_ollabridge_pairing_requires_login(space_client):
    assert space_client.post(
        "/v1/connections/ollabridge/pair", json={"code": "ABCD-1234"}
    ).status_code == 401
    assert space_client.delete("/v1/connections/ollabridge").status_code == 401


def test_space_ollabridge_pairing_stores_only_encrypted_token(space_client, monkeypatch):
    from webapp import api_v1, crypto
    from webapp.database import Connection, SessionLocal

    _login_space_admin(space_client)
    sent = []

    class FakeCloudClient:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, url, json):
            sent.append((url, json))
            from types import SimpleNamespace

            return SimpleNamespace(
                status_code=200,
                json=lambda: {"status": "ok", "device_token": "ob_live_device_secret", "device_id": "unit-test"},
            )

    monkeypatch.setattr(api_v1.httpx, "AsyncClient", FakeCloudClient)
    monkeypatch.setattr(
        api_v1.clients, "test_ollabridge",
        lambda base, token: {
            "status": "ok",
            "detail": "1 model available.",
            "extra": {"models": ["free-best"]},
        },
    )

    paired = space_client.post(
        "/v1/connections/ollabridge/pair", json={"code": "abcd1234"}
    )
    assert paired.status_code == 200, paired.text
    assert paired.json()["pairing"] == "paired"
    assert paired.json()["status"] == "ok"
    assert "ob_live_device_secret" not in paired.text
    assert sent == [(
        "https://app.ollabridge.com/device/pair-simple",
        {"code": "ABCD-1234"},
    )]

    listing = space_client.get("/v1/connections")
    assert listing.status_code == 200
    olla = next(item for item in listing.json() if item["provider"] == "ollabridge")
    assert olla["base_url"] == "https://app.ollabridge.com/v1"
    assert olla["has_secret"] is True
    assert "ob_live_device_secret" not in listing.text

    db = SessionLocal()
    try:
        stored = db.query(Connection).filter_by(provider="ollabridge").first()
        assert stored.api_key_enc != "ob_live_device_secret"
        assert crypto.decrypt(stored.api_key_enc) == "ob_live_device_secret"
    finally:
        db.close()

    removed = space_client.delete("/v1/connections/ollabridge")
    assert removed.status_code == 204
    after = space_client.get("/v1/connections").json()
    olla = next(item for item in after if item["provider"] == "ollabridge")
    assert olla["has_secret"] is False
    assert olla["status"] == "unknown"


def test_space_ollabridge_rejects_invalid_and_failed_pairing(space_client, monkeypatch):
    from webapp import api_v1

    _login_space_admin(space_client)
    assert space_client.post(
        "/v1/connections/ollabridge/pair", json={"code": "BAD"}
    ).status_code == 422

    class FailedCloudClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, url, json):
            from types import SimpleNamespace

            return SimpleNamespace(status_code=200, json=lambda: {"status": "error"})

    monkeypatch.setattr(api_v1.httpx, "AsyncClient", FailedCloudClient)
    rejected = space_client.post(
        "/v1/connections/ollabridge/pair", json={"code": "ABCD-1234"}
    )
    assert rejected.status_code == 422
    assert "pairing failed" in rejected.json()["detail"].lower()
    listing = space_client.get("/v1/connections").json()
    olla = next(item for item in listing if item["provider"] == "ollabridge")
    assert not olla["has_secret"]


def test_space_connector_save_and_test_with_safe_urls(space_client, monkeypatch):
    from webapp import api_v1

    _login_space_admin(space_client)
    checked = []
    def fake_test(provider, base_url, secret):
        checked.append((provider, base_url, secret))
        return {"status": "ok", "detail": "Endpoint reachable.", "extra": {}}

    monkeypatch.setattr(api_v1.clients, "test_provider", fake_test)
    bad = space_client.post(
        "/v1/connections/gitpilot",
        json={"base_url": "https://user:password@example.com", "api_key": "secret"},
    )
    assert bad.status_code == 422
    saved = space_client.post(
        "/v1/connections/gitpilot",
        json={"base_url": "https://gitpilot.example.org/", "api_key": "test-token"},
    )
    assert saved.status_code == 200, saved.text
    tested = space_client.post("/v1/connections/gitpilot/test")
    assert tested.status_code == 200, tested.text
    assert checked == [
        ("gitpilot", "https://gitpilot.example.org", "test-token"),
        ("gitpilot", "https://gitpilot.example.org", "test-token"),
    ]
    connection = next(
        c for c in space_client.get("/v1/connections").json()
        if c["provider"] == "gitpilot"
    )
    assert connection["has_secret"] is True
    assert "test-token" not in str(connection)
