"""Deny-paths rule.

`.selfrepair.yml` lists paths the tool must never touch (migrations, infra,
secrets). This rule enforces that.
"""
from __future__ import annotations

from selfrepair.policy.decisions import (
    PolicyContext,
    PolicyDecision,
    PolicyOutcome,
)
from selfrepair.policy.glob import matches


def deny_paths_rule(ctx: PolicyContext) -> PolicyDecision | None:
    deny_patterns = ctx.repo_config.deny_paths
    if not deny_patterns:
        return None
    for path in ctx.files_changed:
        for pattern in deny_patterns:
            if matches(path, pattern):
                return PolicyDecision(
                    outcome=PolicyOutcome.DENY,
                    rule_id="deny_paths",
                    reason=f"path {path!r} matches deny pattern {pattern!r}",
                )
    return None
