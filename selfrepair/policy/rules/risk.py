"""Risk-based review rule.

A repair classified high or critical risk requires human approval. LLM
repairs are denied unless the repo opted in via `escalate_to_llm` for that
finding kind.
"""
from __future__ import annotations

from selfrepair.policy.decisions import (
    PolicyContext,
    PolicyDecision,
    PolicyOutcome,
)
from selfrepair.sdk.models import Severity

_HIGH_RISK = (Severity.HIGH, Severity.CRITICAL)


def risk_rule(ctx: PolicyContext) -> PolicyDecision | None:
    if ctx.is_llm_repair and not ctx.repo_config.llm_enabled_for(
        ctx.finding.kind
    ):
        return PolicyDecision(
            outcome=PolicyOutcome.DENY,
            rule_id="risk.llm_not_opted_in",
            reason=(
                f"LLM repair attempted for kind={ctx.finding.kind!r} but the "
                "repo has not opted in via escalate_to_llm"
            ),
        )
    if ctx.plan.risk in _HIGH_RISK:
        return PolicyDecision(
            outcome=PolicyOutcome.REVIEW,
            rule_id="risk.high",
            reason=(
                f"plan.risk = {ctx.plan.risk.value} requires human approval"
            ),
            requires_approval=True,
        )
    return None
