"""Hard merge boundary for autonomous routines.

The Routines UI can opt into automatic promotion, but protected branches stay
locked until a human explicitly unlocks the individual routine. Executors must
call evaluate_merge_guard() immediately before any merge operation.
"""
from __future__ import annotations

from dataclasses import dataclass

PROTECTED_BRANCHES = frozenset({"main", "master"})


def is_protected_branch(branch: str | None) -> bool:
    return bool(branch and branch.strip().lower() in PROTECTED_BRANCHES)


@dataclass(frozen=True)
class MergeGuardDecision:
    allowed: bool
    reason: str


def evaluate_merge_guard(
    *,
    target_branch: str,
    execution_mode: str,
    merge_lock: bool,
    checks_ok: bool,
    unresolved_reviews: int,
    human_approved: bool,
) -> MergeGuardDecision:
    """Return whether a routine is allowed to merge right now.

    This is deliberately independent from GitHub/GitLab clients so every
    provider-specific executor can share the same non-bypassable policy.
    """
    protected = is_protected_branch(target_branch)
    if protected and merge_lock:
        return MergeGuardDecision(False, "protected_branch_locked")
    if not checks_ok:
        return MergeGuardDecision(False, "required_checks_not_green")
    if unresolved_reviews > 0:
        return MergeGuardDecision(False, "unresolved_review_threads")
    if execution_mode != "automatic" and not human_approved:
        return MergeGuardDecision(False, "human_approval_required")
    return MergeGuardDecision(True, "merge_allowed")
