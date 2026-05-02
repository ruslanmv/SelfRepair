"""Sigstore commit signing via cosign.

Production uses cosign keyless signing via GitHub OIDC. The bundle is
attached to the repair record so verification can be replayed later
(`cosign verify-blob`).

If cosign isn't installed we log a warning and return None so dev
environments don't blow up. Production callers can pass
`fail_on_missing_signing=True` at the publisher to upgrade this to an error.
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Signature:
    bundle_path: Path
    signed_blob_sha: str


def is_available() -> bool:
    return shutil.which("cosign") is not None


def sign_blob(
    blob_path: Path, *, identity_token: str | None = None
) -> Signature | None:
    """Sign `blob_path` using cosign keyless mode.

    Returns None if cosign isn't installed or the call fails. Callers can
    treat None as "unsigned" or escalate, depending on environment policy.
    """
    if not is_available():
        logger.warning("cosign not installed; skipping signature")
        return None

    bundle_path = blob_path.with_suffix(blob_path.suffix + ".sigstore")
    cmd = [
        "cosign", "sign-blob", "--yes",
        "--bundle", str(bundle_path),
        str(blob_path),
    ]
    env = None
    if identity_token:
        env = {"COSIGN_IDENTITY_TOKEN": identity_token}
    try:
        subprocess.run(cmd, check=True, capture_output=True, env=env)
    except subprocess.CalledProcessError as exc:
        logger.error(
            "cosign sign-blob failed (rc=%s): %s",
            exc.returncode,
            exc.stderr.decode("utf-8", errors="replace"),
        )
        return None
    sha = hashlib.sha256(blob_path.read_bytes()).hexdigest()
    return Signature(bundle_path=bundle_path, signed_blob_sha=sha)


def verify_blob(blob_path: Path, bundle_path: Path) -> bool:
    if not is_available():
        return False
    cmd = [
        "cosign", "verify-blob",
        "--bundle", str(bundle_path),
        str(blob_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as exc:
        logger.error(
            "cosign verify-blob failed: %s",
            exc.stderr.decode("utf-8", errors="replace"),
        )
        return False
