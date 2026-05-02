"""Policy evaluator for CI Guardian.

Phase 1: returns NONE for every classified failure (observability only).
Later phases read `.selfrepair.yml ci_guardian.*` and emit RERUN / REPAIR
/ ESCALATE / SUPPRESS.

Three hard rules apply even in Phase 1:
  * Kill switch wins over everything → NONE.
  * Redacted secret in the diff → ESCALATE (the diff is suspect).
  * Never-auto-repair classes → ESCALATE.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from selfrepair.ci.classifier import FailureClass
from selfrepair.ci.config import CIGuardianRuntime, get_runtime
from selfrepair.config.repo_config import RepoConfig


class CIDecisionAction(StrEnum):
    NONE = "none"            # observability only; do not act
    RERUN = "rerun"          # rerun_failed_jobs on GitHub
    REPAIR = "repair"        # create job(trigger=ci_failure) and enqueue
    ESCALATE = "escalate"    # never auto-act; human review
    SUPPRESS = "suppress"    # storm protection / known noise


@dataclass(frozen=True)
class CIDecision:
    action: CIDecisionAction
    reason: str
    failure_class: FailureClass
    requires_approval: bool = False
    rule_id: str = ""


_NEVER_AUTO_REPAIR: frozenset[FailureClass] = frozenset(
    {
        FailureClass.SECRET_OR_ENV_MISSING,
        FailureClass.PERMISSION_ERROR,
        FailureClass.SECURITY_SCAN_FAILURE,
        FailureClass.UNKNOWN,
    }
)


def evaluate_policy(
    *,
    failure_class: FailureClass,
    repo_config: RepoConfig,
    redacted_secret_count: int = 0,
    runtime: CIGuardianRuntime | None = None,
) -> CIDecision:
    """Decide what to do about a freshly classified CI failure.

    `repo_config` is accepted now even though Phase 1 doesn't read its
    auto_rerun / auto_repair fields. Keeping the signature stable means
    Phase 4 / 5 won't need to touch every call site.
    """
    runtime = runtime or get_runtime()

    if runtime.kill_switch:
        return CIDecision(
            action=CIDecisionAction.NONE,
            reason="kill switch (SELFREPAIR_CI_GUARDIAN_KILL=1)",
            failure_class=failure_class,
            rule_id="kill_switch",
        )

    if redacted_secret_count > 0:
        return CIDecision(
            action=CIDecisionAction.ESCALATE,
            reason=(
                f"diff contains {redacted_secret_count} redacted secret(s); "
                "human review required"
            ),
            failure_class=failure_class,
            requires_approval=True,
            rule_id="safety.secrets_in_diff",
        )

    # The repo can extend the never-repair set in `.selfrepair.yml`.
    repo_never = (
        set(repo_config.ci_guardian.safety.never_repair_classes)
        if repo_config.ci_guardian is not None
        else set()
    )
    if failure_class.value in repo_never or failure_class in _NEVER_AUTO_REPAIR:
        return CIDecision(
            action=CIDecisionAction.ESCALATE,
            reason=f"{failure_class.value} is in the never-auto-repair set",
            failure_class=failure_class,
            requires_approval=True,
            rule_id="safety.never_auto_repair",
        )

    # Phase 1 default: trace only.
    return CIDecision(
        action=CIDecisionAction.NONE,
        reason="phase 1: observability only; no auto-action enabled",
        failure_class=failure_class,
        rule_id="phase1.default",
    )
