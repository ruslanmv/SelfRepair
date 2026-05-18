"""Unit tests for `selfrepair.auth.passwords`.

PBKDF2 hashing + verification is security-critical so cover the
roundtrip, the wrong-password rejection, the rejection of malformed
stored hashes, and the upgrade hint that lets routes rehash older
rows transparently.
"""
from __future__ import annotations

import pytest

from selfrepair.auth.passwords import (
    hash_password,
    needs_rehash,
    verify_password,
)


class TestHashPassword:
    def test_roundtrip_succeeds(self) -> None:
        stored = hash_password("correct-horse-battery-staple")
        assert verify_password(stored, "correct-horse-battery-staple") is True

    def test_wrong_password_rejected(self) -> None:
        stored = hash_password("correct-horse")
        assert verify_password(stored, "wrong-horse") is False

    def test_format_is_self_describing(self) -> None:
        stored = hash_password("hello")
        algo, iters, salt_hex, digest_hex = stored.split("$")
        assert algo == "pbkdf2_sha256"
        assert int(iters) >= 480_000
        assert len(salt_hex) == 32  # 16 bytes hex-encoded
        assert len(digest_hex) == 64  # 32 bytes hex-encoded

    def test_empty_password_raises(self) -> None:
        with pytest.raises(ValueError):
            hash_password("")

    def test_two_hashes_use_different_salts(self) -> None:
        a = hash_password("same-password")
        b = hash_password("same-password")
        assert a != b
        # Both still verify.
        assert verify_password(a, "same-password")
        assert verify_password(b, "same-password")


class TestVerifyPassword:
    @pytest.mark.parametrize(
        "stored",
        [
            "",
            "not-a-hash",
            "pbkdf2_sha256$abc",
            "pbkdf2_sha256$100$bad-hex$bad-hex",
            "argon2$10000$" + "0" * 32 + "$" + "0" * 64,
        ],
    )
    def test_malformed_hashes_return_false(self, stored: str) -> None:
        assert verify_password(stored, "anything") is False

    def test_empty_password_returns_false(self) -> None:
        stored = hash_password("real")
        assert verify_password(stored, "") is False


class TestNeedsRehash:
    def test_current_iterations_do_not_need_rehash(self) -> None:
        stored = hash_password("hello")
        assert needs_rehash(stored) is False

    def test_weaker_iterations_signal_rehash(self) -> None:
        stored = hash_password("hello", iterations=10_000)
        assert needs_rehash(stored, target_iterations=480_000) is True

    @pytest.mark.parametrize("stored", ["", "garbage", "scrypt$1$2$3"])
    def test_unknown_format_signals_rehash(self, stored: str) -> None:
        assert needs_rehash(stored) is True
