"""CI Guardian — additive subsystem for GitHub Actions self-healing.

Per the design, CI Guardian:
  * Listens to workflow_run / workflow_job / check_run / check_suite events.
  * Persists workflow runs and jobs (additive tables; see migration 0002).
  * Redacts secrets BEFORE storing logs (entry gate, not exit gate).
  * Classifies failures with deterministic rules.
  * Computes stable fingerprints so repeat failures collapse to one row.
  * Emits a policy decision; in Phase 1 every decision is NONE
    (observability only, no auto-action).
  * In later phases, decisions of REPAIR create a normal `job` row with
    `trigger=ci_failure` and re-use the existing process_job pipeline.
    There is no second repair engine.
"""
from selfrepair.ci.classifier import Classification, FailureClass, classify_failure
from selfrepair.ci.config import CIGuardianRuntime, get_runtime
from selfrepair.ci.fingerprints import compute_fingerprint, normalize_signature
from selfrepair.ci.policies import CIDecision, CIDecisionAction, evaluate_policy
from selfrepair.ci.redaction import RedactionResult, redact

__all__ = [
    "CIDecision",
    "CIDecisionAction",
    "CIGuardianRuntime",
    "Classification",
    "FailureClass",
    "RedactionResult",
    "classify_failure",
    "compute_fingerprint",
    "evaluate_policy",
    "get_runtime",
    "normalize_signature",
    "redact",
]
