from selfrepair.governance.merge_guard import evaluate_merge_guard


def test_main_is_blocked_while_locked_even_in_automatic_mode():
    decision = evaluate_merge_guard(
        target_branch="main",
        execution_mode="automatic",
        merge_lock=True,
        checks_ok=True,
        unresolved_reviews=0,
        human_approved=False,
    )
    assert decision.allowed is False
    assert decision.reason == "protected_branch_locked"


def test_automatic_unlocked_merge_still_requires_clean_checks_and_reviews():
    failed_checks = evaluate_merge_guard(
        target_branch="master",
        execution_mode="automatic",
        merge_lock=False,
        checks_ok=False,
        unresolved_reviews=0,
        human_approved=False,
    )
    unresolved = evaluate_merge_guard(
        target_branch="master",
        execution_mode="automatic",
        merge_lock=False,
        checks_ok=True,
        unresolved_reviews=1,
        human_approved=False,
    )
    assert failed_checks.reason == "required_checks_not_green"
    assert unresolved.reason == "unresolved_review_threads"


def test_human_review_mode_requires_human_approval():
    decision = evaluate_merge_guard(
        target_branch="develop",
        execution_mode="human_review",
        merge_lock=False,
        checks_ok=True,
        unresolved_reviews=0,
        human_approved=False,
    )
    assert decision.allowed is False
    assert decision.reason == "human_approval_required"


def test_automatic_unlocked_clean_merge_is_allowed():
    decision = evaluate_merge_guard(
        target_branch="master",
        execution_mode="automatic",
        merge_lock=False,
        checks_ok=True,
        unresolved_reviews=0,
        human_approved=False,
    )
    assert decision.allowed is True
    assert decision.reason == "merge_allowed"
