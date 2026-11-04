"""Shared connector rules: pairing, SSRF, encryption, and truthful probes."""

from __future__ import annotations

import pytest

from selfrepair.connectors.runtime import ResolvedService, resolve_service
from selfrepair.connectors.service import (
    ConnectorError,
    ConnectorState,
    apply_disconnect,
    apply_probe,
    assert_mutation_origin,
    assert_public_resolution,
    decrypt,
    display_status,
    encrypt,
    interpret_pairing_response,
    merged_secret,
    normalize_pairing_code,
    pairing_request_body,
    pairing_submission,
    probe_gitpilot,
    probe_matrixlab,
    probe_ollabridge,
    public_view,
    rate_limit,
    reset_rate_limits,
    validate_service_url,
)


@pytest.fixture(autouse=True)
def _dev_key(monkeypatch):
    monkeypatch.setenv("SELFREPAIR_ENV", "test")
    reset_rate_limits()


def test_pairing_code_and_request_identify_selfrepair():
    assert normalize_pairing_code(" abcd1234 ") == "ABCD-1234"
    body = pairing_request_body("ABCD-1234")
    assert body["code"] == "ABCD-1234"
    assert body["client"]["name"] == "SelfRepair"
    assert body["client"]["vendor"] == "ruslanmv"
    with pytest.raises(ConnectorError):
        normalize_pairing_code("NOPE")


def test_pairing_response_hides_token_and_maps_failures():
    token = interpret_pairing_response(
        200, {"status": "ok", "device_token": "device-secret", "device_id": "dev_1"}
    )
    assert token == "device-secret"
    with pytest.raises(ConnectorError, match="expired"):
        interpret_pairing_response(200, {"status": "error", "error": "Pairing code expired"})
    with pytest.raises(ConnectorError, match="already used"):
        interpret_pairing_response(200, {"status": "error", "error": "Code already used"})
    with pytest.raises(ConnectorError, match="Sign in"):
        interpret_pairing_response(
            200,
            {"status": "error", "error": "Pairing code is not linked to an authenticated account."},
        )
    with pytest.raises(ConnectorError, match="Pairing failed"):
        interpret_pairing_response(200, ["not-an-object"])
    with pytest.raises(ConnectorError, match="rate-limited"):
        interpret_pairing_response(429, {"status": "error"})


def test_encryption_round_trip_and_public_view_omits_secret():
    stored = encrypt("device-secret-value")
    assert stored != "device-secret-value"
    assert decrypt(stored) == "device-secret-value"
    state = ConnectorState(
        provider="ollabridge",
        base_url="https://app.ollabridge.com/v1",
        secret="device-secret-value",
        status="ok",
    )
    view = public_view("ollabridge", state)
    assert view["has_secret"] is True
    assert "device-secret-value" not in str(view)
    assert view["display_status"] == "Connected"
    assert view["workflow_verified"] is False


def test_production_refuses_dev_encryption_fallback(monkeypatch):
    monkeypatch.delenv("SELFREPAIR_ENV", raising=False)
    monkeypatch.delenv("SELFREPAIR_SECRET_KEY", raising=False)
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    monkeypatch.delenv("SELFREPAIR_INSECURE_COOKIES", raising=False)
    with pytest.raises(ConnectorError, match="SELFREPAIR_SECRET_KEY"):
        encrypt("token")


def test_unsafe_urls_and_private_dns_are_rejected(monkeypatch):
    for raw in (
        "http://gitpilot.example",
        "https://user:pw@gitpilot.example",
        "https://169.254.169.254/latest",
        "https://10.0.0.8",
        "https://metadata.google.internal",
        "file:///etc/passwd",
    ):
        with pytest.raises(ConnectorError):
            validate_service_url(raw)
    assert (
        validate_service_url("https://gitpilot.example.org/v1") == "https://gitpilot.example.org/v1"
    )

    import selfrepair.connectors.service as loaded

    def fake_addr(*_args, **_kwargs):
        return [(None, None, None, None, ("10.1.1.1", 443))]

    monkeypatch.setattr(loaded._impl.socket, "getaddrinfo", fake_addr)
    with pytest.raises(ConnectorError, match="private"):
        assert_public_resolution("https://gitpilot.example.org")


def test_cross_site_origin_is_blocked_and_same_host_is_allowed():
    with pytest.raises(ConnectorError, match="origin"):
        assert_mutation_origin({"origin": "https://evil.example"}, host="selfrepair.example")
    with pytest.raises(ConnectorError, match="Cross-site"):
        assert_mutation_origin({"sec-fetch-site": "cross-site"}, host="selfrepair.example")
    assert_mutation_origin({"origin": "https://selfrepair.example"}, host="selfrepair.example")
    assert_mutation_origin({}, host="selfrepair.example")


def test_rate_limit_and_overlapping_pairing():
    allowed = [rate_limit("pair", "user", limit=2, window_seconds=60) for _ in range(3)]
    assert allowed == [True, True, False]
    with pairing_submission("user-1"):
        with pytest.raises(ConnectorError, match="already in progress"):
            with pairing_submission("user-1"):
                pass
    with pairing_submission("user-1"):
        pass


def test_gitpilot_health_is_not_a_completed_repair():
    def getter(url, headers):
        assert headers["Authorization"] == "Bearer saved"
        return 200, {"status": "ok", "version": "1.2.3"}

    result = probe_gitpilot("https://gitpilot.example.org", "saved", getter=getter)
    assert result["status"] == "reachable"
    assert result["workflow_verified"] is False
    assert "repair was not submitted" in result["detail"]


def test_matrixlab_profiles_do_not_count_as_execution():
    def getter(url, headers):
        if url.endswith("/capabilities"):
            return 200, {"profiles": ["python-repair", "node-test"]}
        return 404, {}

    result = probe_matrixlab("https://matrix.example.org", "", getter=getter)
    assert result["status"] == "reachable"
    assert result["extra"]["profiles"] == ["python-repair", "node-test"]
    assert result["workflow_verified"] is False


def test_ollabridge_model_list_verifies_access_only():
    def getter(url, headers):
        assert url.endswith("/models")
        assert headers["Authorization"] == "Bearer device"
        return 200, {"data": [{"id": "free-best"}]}

    result = probe_ollabridge("https://app.ollabridge.com/v1", "device", getter=getter)
    assert result["status"] == "ok"
    assert result["access_verified"] is True
    assert result["workflow_verified"] is False


def test_blank_token_keeps_saved_secret_and_disconnect_clears_it():
    previous = ConnectorState(
        provider="gitpilot",
        base_url="https://gitpilot.example.org",
        secret="kept-token",
        status="reachable",
    )
    assert merged_secret(previous.secret, "  ") == "kept-token"
    updated = apply_probe(
        previous,
        provider="gitpilot",
        base_url="https://gitpilot.example.org",
        secret=merged_secret(previous.secret, None),
        auth_method="key",
        probe={"status": "reachable", "detail": "health only"},
    )
    assert updated.secret == "kept-token"
    assert updated.last_attempted_at is not None
    assert updated.last_checked_at is not None
    cleared = apply_disconnect(updated, "gitpilot")
    assert cleared.secret == ""
    assert cleared.status == "disconnected"
    assert display_status(cleared) == "Disconnected"


def test_resolver_prefers_saved_row_and_does_not_revive_env_token(monkeypatch):
    monkeypatch.setenv("GITPILOT_URL", "https://env.example")
    monkeypatch.setenv("GITPILOT_TOKEN", "env-token")

    def loader(provider, org_id):
        assert provider == "gitpilot"
        assert org_id == "org-1"
        return ConnectorState(
            provider="gitpilot",
            base_url="https://saved.example",
            secret="",
            status="disconnected",
        )

    saved = resolve_service("gitpilot", org_id="org-1", loader=loader)
    assert saved.source == "saved"
    assert saved.base_url == "https://saved.example"
    assert saved.token is None

    fallback = resolve_service("gitpilot", org_id=None)
    assert fallback == ResolvedService(
        provider="gitpilot",
        base_url="https://env.example",
        token="env-token",
        source="environment",
        detail="",
    )


def test_full_api_registers_the_same_connection_routes():
    from selfrepair.api.main import app

    paths: set[str] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        if path:
            paths.add(path)
        original = getattr(route, "original_router", None)
        for sub in getattr(original, "routes", []) or []:
            sub_path = getattr(sub, "path", None)
            if sub_path:
                paths.add(sub_path)
    assert "/v1/connections" in paths
    assert "/v1/connections/ollabridge/pair" in paths
    assert "/v1/connections/{provider}" in paths
    assert "/v1/connections/{provider}/test" in paths


def test_resolver_rejects_private_saved_url():
    def loader(_provider, _org):
        return ConnectorState(
            provider="matrixlab", base_url="https://10.2.2.2", secret="tok", status="ok"
        )

    resolved = resolve_service("matrixlab", org_id="org-1", loader=loader)
    assert resolved.source == "rejected"
    assert resolved.token is None
    assert resolved.base_url == ""
