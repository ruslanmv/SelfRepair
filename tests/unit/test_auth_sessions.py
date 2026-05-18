"""Unit tests for `selfrepair.auth.sessions` token primitives.

The DB-touching helpers (create_session / lookup_session / etc.) are
exercised by the integration suite. Here we cover the pure functions.
"""
from __future__ import annotations

from selfrepair.auth.sessions import generate_token, hash_token


class TestGenerateToken:
    def test_returns_url_safe_string(self) -> None:
        token = generate_token()
        assert isinstance(token, str)
        # secrets.token_urlsafe(32) yields ~43 chars of base64url.
        assert len(token) >= 32
        assert all(c.isalnum() or c in {"-", "_"} for c in token)

    def test_unique_per_call(self) -> None:
        tokens = {generate_token() for _ in range(50)}
        assert len(tokens) == 50


class TestHashToken:
    def test_deterministic(self) -> None:
        assert hash_token("abc") == hash_token("abc")

    def test_collision_resistant(self) -> None:
        assert hash_token("abc") != hash_token("abd")

    def test_format_is_hex_sha256(self) -> None:
        h = hash_token("hello")
        assert len(h) == 64
        int(h, 16)
