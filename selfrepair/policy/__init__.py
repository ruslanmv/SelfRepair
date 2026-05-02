"""Policy engine for repair decisions.

Per ADR-0001 / system-design.md §6. Defaults are conservative: without
explicit opt-in in `.selfrepair.yml`, the engine returns REVIEW or DENY
for non-trivial changes.

The engine here is a Python runtime that consumes the same inputs as the
bundled Rego policies in `selfrepair/policy/bundle/`. The Rego bundle is
the future migration target when OPA is wired in as a sidecar; the Python
rules will then be replaced with HTTP calls to OPA behind the same
interface.
"""
from selfrepair.policy.decisions import (
    PolicyContext,
    PolicyDecision,
    PolicyOutcome,
)
from selfrepair.policy.engine import PolicyEngine, default_engine

__all__ = [
    "PolicyContext",
    "PolicyDecision",
    "PolicyEngine",
    "PolicyOutcome",
    "default_engine",
]
