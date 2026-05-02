import time
from datetime import UTC, datetime, timedelta

import pytest

pyjwt = pytest.importorskip("jwt")
cryptography = pytest.importorskip("cryptography")

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

from selfrepair.auth.github_app import (  # noqa: E402
    GitHubAppAuth,
    InstallationToken,
    verify_webhook_signature,
)


@pytest.fixture(scope="module")
def rsa_keypair() -> tuple[str, bytes]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


class TestAppJwt:
    def test_jwt_issuer_is_app_id(self, rsa_keypair) -> None:
        private_pem, public_pem = rsa_keypair
        auth = GitHubAppAuth(app_id="12345", private_key_pem=private_pem)
        token = auth.app_jwt()
        decoded = pyjwt.decode(token, public_pem, algorithms=["RS256"])
        assert decoded["iss"] == "12345"

    def test_jwt_lifetime_within_github_limit(self, rsa_keypair) -> None:
        private_pem, public_pem = rsa_keypair
        auth = GitHubAppAuth(app_id="x", private_key_pem=private_pem)
        token = auth.app_jwt()
        decoded = pyjwt.decode(token, public_pem, algorithms=["RS256"])
        # GitHub allows max 10 minutes; we use 9 plus a 60s backdate.
        assert decoded["exp"] - decoded["iat"] <= 11 * 60

    def test_jwt_iat_is_backdated_for_clock_skew(self, rsa_keypair) -> None:
        private_pem, _ = rsa_keypair
        auth = GitHubAppAuth(app_id="x", private_key_pem=private_pem)
        token = auth.app_jwt()
        decoded = pyjwt.decode(token, options={"verify_signature": False})
        assert decoded["iat"] <= int(time.time())


class TestInstallationTokenExpiry:
    def test_expired_when_within_refresh_margin(self) -> None:
        # 5 min margin; 2 min from now should already be "expired".
        token = InstallationToken(
            token="t", expires_at=datetime.now(UTC) + timedelta(minutes=2)
        )
        assert token.is_expired

    def test_not_expired_when_well_in_future(self) -> None:
        token = InstallationToken(
            token="t", expires_at=datetime.now(UTC) + timedelta(hours=1)
        )
        assert not token.is_expired

    def test_expired_when_already_past(self) -> None:
        token = InstallationToken(
            token="t", expires_at=datetime.now(UTC) - timedelta(minutes=1)
        )
        assert token.is_expired


class TestWebhookSignature:
    SECRET = b"top-secret"

    def _sign(self, body: bytes) -> str:
        import hashlib
        import hmac

        return "sha256=" + hmac.new(self.SECRET, body, hashlib.sha256).hexdigest()

    def test_valid_signature_passes(self) -> None:
        body = b'{"hello": "world"}'
        assert verify_webhook_signature(
            secret=self.SECRET, payload=body, header=self._sign(body)
        )

    def test_tampered_body_fails(self) -> None:
        signed_for = b'{"hello": "world"}'
        actual = b'{"hello": "evil"}'
        assert not verify_webhook_signature(
            secret=self.SECRET, payload=actual, header=self._sign(signed_for)
        )

    def test_missing_header_fails(self) -> None:
        assert not verify_webhook_signature(
            secret=self.SECRET, payload=b"x", header=None
        )

    def test_wrong_prefix_fails(self) -> None:
        assert not verify_webhook_signature(
            secret=self.SECRET, payload=b"x", header="md5=" + "0" * 32
        )

    def test_secret_can_be_str_or_bytes(self) -> None:
        body = b"x"
        sig = self._sign(body)
        assert verify_webhook_signature(secret=self.SECRET, payload=body, header=sig)
        assert verify_webhook_signature(
            secret="top-secret", payload=body, header=sig
        )
