"""Unit tests for `selfrepair.api.middleware`.

The middleware stack is the security/correctness gate for every
mutating endpoint. Cover the request-id contract, the rate-limit
allowlist matching, and the idempotency fingerprinting helper.
The Redis-backed paths fail open in production and are exercised in
the integration suite once a Redis service is available.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from selfrepair.api.middleware import (
    REQUEST_ID_HEADER,
    RequestIdMiddleware,
    _idem_fingerprint,
    _match_rule,
)


class TestRequestIdMiddleware:
    @pytest.fixture
    def app(self) -> FastAPI:
        app = FastAPI()
        app.add_middleware(RequestIdMiddleware)

        @app.get("/echo")
        def echo(request: Request) -> dict[str, str]:
            return {"rid": request.state.request_id}

        return app

    def test_generates_id_when_absent(self, app: FastAPI) -> None:
        client = TestClient(app)
        resp = client.get("/echo")
        assert resp.status_code == 200
        rid = resp.headers.get(REQUEST_ID_HEADER)
        assert rid
        # UUID-ish (32 hex + 4 dashes = 36 chars). We don't enforce
        # uuid4 specifically — the contract is "stable id per request".
        assert len(rid) >= 16
        assert resp.json()["rid"] == rid

    def test_echoes_inbound_id(self, app: FastAPI) -> None:
        client = TestClient(app)
        resp = client.get("/echo", headers={REQUEST_ID_HEADER: "trace-abc-123"})
        assert resp.status_code == 200
        assert resp.headers[REQUEST_ID_HEADER] == "trace-abc-123"
        assert resp.json()["rid"] == "trace-abc-123"


class TestRateRuleMatch:
    @pytest.mark.parametrize(
        "method,path,expected",
        [
            ("POST", "/v1/auth/login", "auth.login"),
            ("POST", "/v1/auth/login/", "auth.login"),
            ("POST", "/v1/jobs", "jobs.create"),
            ("POST", "/v1/jobs/some-id/cancel", "jobs.create"),
            ("POST", "/v1/issues/sync", "issues.sync"),
            # GET on a rate-limited POST path is unaffected.
            ("GET", "/v1/auth/login", None),
            # Random POSTs aren't rate-limited.
            ("POST", "/v1/findings/abc/suppress", None),
        ],
    )
    def test_match_table(self, method: str, path: str, expected: str | None) -> None:
        rule = _match_rule(method, path)
        assert (rule.name if rule else None) == expected


class TestIdempotencyFingerprint:
    def test_same_inputs_yield_same_fingerprint(self) -> None:
        a = _idem_fingerprint(
            org_id="org-1", method="POST", path="/v1/jobs", key="K"
        )
        b = _idem_fingerprint(
            org_id="org-1", method="POST", path="/v1/jobs", key="K"
        )
        assert a == b

    def test_different_orgs_dont_collide(self) -> None:
        a = _idem_fingerprint(
            org_id="org-1", method="POST", path="/v1/jobs", key="K"
        )
        b = _idem_fingerprint(
            org_id="org-2", method="POST", path="/v1/jobs", key="K"
        )
        assert a != b

    def test_different_methods_dont_collide(self) -> None:
        a = _idem_fingerprint(
            org_id="org-1", method="POST", path="/v1/jobs", key="K"
        )
        b = _idem_fingerprint(
            org_id="org-1", method="DELETE", path="/v1/jobs", key="K"
        )
        assert a != b

    def test_fingerprint_is_hex_sha256(self) -> None:
        fp = _idem_fingerprint(
            org_id="org-1", method="POST", path="/v1/jobs", key="K"
        )
        assert len(fp) == 64
        int(fp, 16)  # raises ValueError if not hex
