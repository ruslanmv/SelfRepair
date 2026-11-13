"""Load the single connector implementation used by both deployments.

The Hugging Face image build context is ``deploy/huggingface``, so the
implementation file lives in that tree. Importing it here keeps the full
FastAPI backend on the same pairing, probe, encryption, and URL rules.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_IMPL_PATH = (
    Path(__file__).resolve().parents[2]
    / "deploy"
    / "huggingface"
    / "webapp"
    / "connector_service.py"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "selfrepair.connectors._service_impl",
        _IMPL_PATH,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"connector service is missing at {_IMPL_PATH}")
    module = importlib.util.module_from_spec(spec)
    # dataclass looks the class up in sys.modules while the body executes.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_impl = _load()

CLOUD_API_BASE = _impl.CLOUD_API_BASE
CLOUD_ORIGIN = _impl.CLOUD_ORIGIN
CLOUD_PAIR_URL = _impl.CLOUD_PAIR_URL
DEFAULTS = _impl.DEFAULTS
LABELS = _impl.LABELS
PROVIDERS = _impl.PROVIDERS
ConnectorError = _impl.ConnectorError
ConnectorState = _impl.ConnectorState
apply_disconnect = _impl.apply_disconnect
apply_probe = _impl.apply_probe
assert_mutation_origin = _impl.assert_mutation_origin
assert_public_resolution = _impl.assert_public_resolution
decrypt = _impl.decrypt
display_status = _impl.display_status
encrypt = _impl.encrypt
ensure_encryption_configured = _impl.ensure_encryption_configured
interpret_pairing_response = _impl.interpret_pairing_response
mask = _impl.mask
merged_secret = _impl.merged_secret
normalize_pairing_code = _impl.normalize_pairing_code
pairing_request_body = _impl.pairing_request_body
pairing_submission = _impl.pairing_submission
probe_gitpilot = _impl.probe_gitpilot
probe_matrixlab = _impl.probe_matrixlab
probe_ollabridge = _impl.probe_ollabridge
probe_provider = _impl.probe_provider
public_view = _impl.public_view
rate_limit = _impl.rate_limit
reset_rate_limits = _impl.reset_rate_limits
response_payload = _impl.response_payload
validate_service_url = _impl.validate_service_url

__all__ = [
    "CLOUD_API_BASE",
    "CLOUD_ORIGIN",
    "CLOUD_PAIR_URL",
    "DEFAULTS",
    "LABELS",
    "PROVIDERS",
    "ConnectorError",
    "ConnectorState",
    "apply_disconnect",
    "apply_probe",
    "assert_mutation_origin",
    "assert_public_resolution",
    "decrypt",
    "display_status",
    "encrypt",
    "ensure_encryption_configured",
    "interpret_pairing_response",
    "mask",
    "merged_secret",
    "normalize_pairing_code",
    "pairing_request_body",
    "pairing_submission",
    "probe_gitpilot",
    "probe_matrixlab",
    "probe_ollabridge",
    "probe_provider",
    "public_view",
    "rate_limit",
    "reset_rate_limits",
    "response_payload",
    "validate_service_url",
]
