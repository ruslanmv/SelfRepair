"""CODEOWNERS rule.

When `codeowners_required` is true (default), any repair touching files with
CODEOWNERS entries must surface the owners as required reviewers. This rule
produces REVIEW (not DENY) so the PR opens but waits for sign-off.

The actual owner lookup happens in `selfrepair.git.codeowners`. This rule
only encodes the policy: "if codeowners_required and files were changed,
require approval before merge".
"""
from __future__ import annotations

from selfrepair.policy.decisions import (
    PolicyContext,
    PolicyDecision,
    PolicyOutcome,
)


def codeowners_rule(ctx: PolicyContext) -> PolicyDecision | None:
    if not ctx.repo_config.codeowners_required:
        return None
    if not ctx.files_changed:
        return None
    return PolicyDecision(
        outcome=PolicyOutcome.REVIEW,
        rule_id="codeowners.required",
        reason=(
            f"codeowners_required=true and {len(ctx.files_changed)} file(s) "
            "changed; CODEOWNERS reviewers will be requested"
        ),
        requires_approval=True,
    )
