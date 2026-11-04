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
