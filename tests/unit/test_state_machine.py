from itertools import pairwise

import pytest

from selfrepair.state.machine import (
    InvalidTransition,
    JobState,
    assert_transition,
    can_transition,
    next_states,
)


class TestStateMachine:
    def test_happy_path_walks_through_pipeline(self) -> None:
        path = [
            JobState.QUEUED,
            JobState.CLONING,
            JobState.ANALYZING,
            JobState.SCANNING,
            JobState.PLANNING,
            JobState.REPAIRING,
            JobState.VALIDATING,
            JobState.PUBLISHING,
            JobState.AWAITING_REVIEW,
            JobState.MERGED,
        ]
        for current, target in pairwise(path):
            assert can_transition(current, target), (
                f"{current} → {target} should be allowed"
            )

    def test_planning_can_short_circuit_to_completed_when_no_findings(self) -> None:
        assert can_transition(JobState.PLANNING, JobState.COMPLETED)

    def test_validation_failure_routes_to_failed_validation(self) -> None:
        assert can_transition(JobState.VALIDATING, JobState.FAILED_VALIDATION)

    def test_failed_validation_can_escalate_or_close(self) -> None:
        assert can_transition(JobState.FAILED_VALIDATION, JobState.ESCALATED)
        assert can_transition(JobState.FAILED_VALIDATION, JobState.CLOSED)

    def test_terminal_states_have_no_outgoing_transitions(self) -> None:
        for terminal in (JobState.COMPLETED, JobState.MERGED, JobState.CLOSED):
            assert next_states(terminal) == frozenset()

    def test_cannot_skip_states(self) -> None:
        assert not can_transition(JobState.QUEUED, JobState.REPAIRING)
        assert not can_transition(JobState.CLONING, JobState.PUBLISHING)

    def test_cannot_go_backwards(self) -> None:
        assert not can_transition(JobState.REPAIRING, JobState.PLANNING)
        assert not can_transition(JobState.MERGED, JobState.AWAITING_REVIEW)

    def test_assert_transition_raises_with_helpful_message(self) -> None:
        with pytest.raises(InvalidTransition) as exc:
            assert_transition(JobState.QUEUED, JobState.MERGED)
        message = str(exc.value)
        assert "queued → merged" in message
        assert "cloning" in message

    def test_any_active_state_can_escalate(self) -> None:
        active = [
            JobState.QUEUED,
            JobState.CLONING,
            JobState.ANALYZING,
            JobState.SCANNING,
            JobState.PLANNING,
            JobState.REPAIRING,
            JobState.VALIDATING,
            JobState.PUBLISHING,
        ]
        for state in active:
            assert can_transition(state, JobState.ESCALATED), (
                f"{state.value} should be able to escalate on unhandled error"
            )

    def test_awaiting_review_can_go_stale(self) -> None:
        assert can_transition(JobState.AWAITING_REVIEW, JobState.STALE)
        assert can_transition(JobState.STALE, JobState.CLOSED)
