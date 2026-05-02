"""LLM budget rule.

Per-repo `monthly_usd` budget in `.selfrepair.yml` is a hard cap on LLM
spend. If the estimated cost of this repair would push spend over the cap,
the repair is denied with a reason that surfaces in the PR comment.

Deterministic repairs (no LLM) skip this rule.
"""
from __future__ import annotations

from selfrepair.policy.decisions import (
    PolicyContext,
    PolicyDecision,
    PolicyOutcome,
)


def budget_rule(ctx: PolicyContext) -> PolicyDecision | None:
    if not ctx.is_llm_repair:
        return None
    cap = ctx.repo_config.budget.monthly_usd
    if cap <= 0:
        return PolicyDecision(
            outcome=PolicyOutcome.DENY,
            rule_id="budget.no_llm_budget",
            reason="LLM repair requested but monthly_usd budget is 0",
        )
    projected = ctx.spent_this_month_usd + ctx.estimated_cost_usd
    if projected > cap:
        return PolicyDecision(
            outcome=PolicyOutcome.DENY,
            rule_id="budget.exceeded",
            reason=(
                f"LLM repair would push spend to ${projected:.2f}, "
                f"over the monthly cap of ${cap:.2f}"
            ),
        )
    return None
