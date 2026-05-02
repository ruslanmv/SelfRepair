"""Policy types: context, decisions, outcomes."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from selfrepair.config.repo_config import RepoConfig
from selfrepair.sdk.models import Finding, RepairPlan


class PolicyOutcome(StrEnum):
    ALLOW = "allow"
    REVIEW = "review"
    DENY = "deny"


@dataclass(frozen=True)
class PolicyContext:
    """Inputs handed to the policy engine.

    Stable across rule evaluations; rules don't mutate it.
    """

    finding: Finding
    plan: RepairPlan
    repo_config: RepoConfig
    files_changed: tuple[str, ...]
    is_llm_repair: bool
    estimated_cost_usd: float = 0.0
    spent_this_month_usd: float = 0.0


@dataclass(frozen=True)
class PolicyDecision:
    outcome: PolicyOutcome
    rule_id: str
    reason: str
    requires_approval: bool = False
