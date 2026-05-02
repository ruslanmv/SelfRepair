from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from selfrepair.git.sigstore import sign_blob, verify_blob


class TestSignBlob:
    def test_returns_none_when_cosign_missing(self, tmp_path: Path) -> None:
        blob = tmp_path / "blob.txt"
        blob.write_text("hello")
        with patch(
            "selfrepair.git.sigstore.is_available", return_value=False
        ):
            assert sign_blob(blob) is None

    def test_returns_signature_on_success(self, tmp_path: Path) -> None:
        blob = tmp_path / "blob.txt"
        blob.write_text("hello")
        with patch(
            "selfrepair.git.sigstore.is_available", return_value=True
        ), patch(
            "selfrepair.git.sigstore.subprocess.run", return_value=None
        ):
            sig = sign_blob(blob)
        assert sig is not None
        assert sig.bundle_path == blob.with_suffix(".txt.sigstore")
        assert len(sig.signed_blob_sha) == 64  # sha256 hex

    def test_returns_none_on_cosign_failure(self, tmp_path: Path) -> None:
        blob = tmp_path / "blob.txt"
        blob.write_text("hello")
        with patch(
            "selfrepair.git.sigstore.is_available", return_value=True
        ), patch(
            "selfrepair.git.sigstore.subprocess.run",
            side_effect=subprocess.CalledProcessError(
                1, "cosign", b"", b"err"
            ),
        ):
            assert sign_blob(blob) is None


class TestVerifyBlob:
    def test_returns_false_when_cosign_missing(self, tmp_path: Path) -> None:
        with patch(
            "selfrepair.git.sigstore.is_available", return_value=False
        ):
            assert (
                verify_blob(tmp_path / "a", tmp_path / "a.sigstore") is False
            )
