"""Redaction is the entry gate for every CI log.

These tests assert two design contracts:
  * concrete secret patterns are redacted to a stable token
  * the same secret produces the same token, so fingerprints stay stable
"""
from __future__ import annotations

import pytest

pytest.importorskip("selfrepair")

from selfrepair.ci.redaction import redact  # noqa: E402


class TestSpecificPatterns:
    @pytest.mark.parametrize(
        "secret, kind",
        [
            ("AKIAIOSFODNN7EXAMPLE", "aws_access_key"),
            ("ghp_" + "a" * 40, "github_classic"),
            ("ghs_" + "b" * 40, "github_server"),
            ("gho_" + "c" * 40, "github_oauth"),
            ("ghu_" + "d" * 40, "github_user"),
            ("ghr_" + "e" * 40, "github_refresh"),
            ("glpat-" + "x" * 25, "gitlab_pat"),
            ("hf_" + "z" * 40, "hf_token"),
            ("sk-" + "k" * 40, "openai_or_claude"),
            ("sk-ant-" + "k" * 40, "openai_or_claude"),
            ("npm_" + "p" * 40, "npm_token"),
        ],
    )
    def test_token_is_redacted(self, secret: str, kind: str) -> None:
        # Primary contract: the literal secret never survives. Some kinds
        # (hf_token, npm_token) generate REDACTED markers that contain the
        # word "token", which a later kv_secret pass re-matches; we don't
        # rely on the textual marker shape, only on classes_seen + the
        # absence of the original secret.
        out = redact(f"some log {secret} more")
        assert secret not in out.text
        assert "<<REDACTED:" in out.text
        assert kind in out.classes_seen

    def test_url_embedded_credentials_are_redacted(self) -> None:
        out = redact("git push https://user:hunter2@github.com/octo/x")
        assert "hunter2" not in out.text
        assert "<<REDACTED:url_cred:" in out.text

    def test_authorization_header_is_redacted(self) -> None:
        out = redact("Authorization: Bearer abcdef.ghijkl.mnopqr")
        # The auth_header regex matches `Header: <next-token>`; we only
        # require the header line itself to be redacted.
        assert "<<REDACTED:auth_header:" in out.text
        assert "auth_header" in out.classes_seen


class TestStability:
    def test_same_secret_yields_same_token(self) -> None:
        secret = "ghp_" + "a" * 40
        a = redact(f"first occurrence {secret}").text
        b = redact(f"different prefix {secret}").text
        # The redacted token must be byte-identical so the downstream
        # fingerprint hasher sees the same input across runs.
        a_token = a.split(" ")[-1]
        b_token = b.split(" ")[-1]
        assert a_token == b_token

    def test_empty_input_returns_empty(self) -> None:
        out = redact("")
        assert out.text == ""
        assert out.secrets_found == 0


class TestEntropyFallback:
    def test_high_entropy_token_is_redacted(self) -> None:
        # Use a non-repeating base64-shape blob so Shannon entropy clears
        # the threshold (a repeating pattern would not).
        import secrets

        random_blob = secrets.token_urlsafe(48)
        out = redact(f"unknown=  {random_blob}  ")
        assert "<<REDACTED:" in out.text
        assert "high_entropy" in out.classes_seen

    def test_short_low_entropy_text_is_left_alone(self) -> None:
        out = redact("the quick brown fox jumps over the lazy dog")
        assert out.secrets_found == 0
        assert "REDACTED" not in out.text
