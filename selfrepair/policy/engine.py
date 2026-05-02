"""Policy engine that evaluates a repair against `.selfrepair.yml` rules.

Rules evaluate in order; the first rule that produces a non-ALLOW decision
wins. ALLOW is the default if every rule passes.

To migrate to OPA later: keep this interface, replace `evaluate()` with a
call to the OPA sidecar (`POST http://opa:8181/v1/data/selfrepair/repair`).
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from selfrepair.policy.decisions import (
    PolicyContext,
    PolicyDecision,
    PolicyOutcome,
)

logger = logging.getLogger(__name__)

Rule = Callable[[PolicyContext], "PolicyDecision | None"]


class PolicyEngine:
    """Composes a list of rules. Evaluation short-circuits on first non-ALLOW."""

    def __init__(self, rules: list[Rule]) -> None:
        self._rules = rules

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
        for rule in self._rules:
            decision = rule(ctx)
            if decision is None or decision.outcome == PolicyOutcome.ALLOW:
                continue
            logger.info(
                "policy decision: rule=%s outcome=%s reason=%s",
                decision.rule_id, decision.outcome.value, decision.reason,
            )
            return decision
        return PolicyDecision(
            outcome=PolicyOutcome.ALLOW,
            rule_id="default",
            reason="all rules passed",
        )


def default_engine() -> PolicyEngine:
    """Build the default engine with all bundled rules."""
    from selfrepair.policy.rules.budget import budget_rule
    from selfrepair.policy.rules.codeowners import codeowners_rule
    from selfrepair.policy.rules.paths import deny_paths_rule
    from selfrepair.policy.rules.risk import risk_rule

    return PolicyEngine(
        [
            deny_paths_rule,    # cheapest, hardest no
            budget_rule,        # cost gate before any LLM work
            risk_rule,          # high-risk and LLM opt-in checks
            codeowners_rule,    # touched files need owner notice
        ]
    )
