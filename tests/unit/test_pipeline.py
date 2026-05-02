import asyncio
import uuid

import pytest

from selfrepair.state.machine import JobState
from selfrepair.worker.pipeline import (
    RepairPipeline,
    StageContext,
    StageResult,
)


def _ctx(state: JobState) -> StageContext:
    return StageContext(
        job_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        repo_id=uuid.uuid4(),
        state=state,
        session=None,  # type: ignore[arg-type]
    )


class TestRepairPipeline:
    def test_unregistered_state_raises_lookup_error(self) -> None:
        pipeline = RepairPipeline()
        with pytest.raises(LookupError, match="no handler"):
            asyncio.run(pipeline.step(_ctx(JobState.CLONING)))

    def test_registered_handler_is_invoked_with_context(self) -> None:
        pipeline = RepairPipeline()
        captured = {}

        async def handler(ctx: StageContext) -> StageResult:
            captured["state"] = ctx.state
            return StageResult(next_state=JobState.ANALYZING, message="cloned")

        pipeline.register(JobState.CLONING, handler)
        result = asyncio.run(pipeline.step(_ctx(JobState.CLONING)))
        assert captured["state"] is JobState.CLONING
        assert result.next_state is JobState.ANALYZING
        assert result.message == "cloned"

    def test_has_handler_reflects_registration(self) -> None:
        pipeline = RepairPipeline()

        async def handler(ctx: StageContext) -> StageResult:
            return StageResult(next_state=JobState.COMPLETED)

        assert not pipeline.has_handler(JobState.PLANNING)
        pipeline.register(JobState.PLANNING, handler)
        assert pipeline.has_handler(JobState.PLANNING)

    def test_register_replaces_previous_handler(self) -> None:
        pipeline = RepairPipeline()

        async def first(ctx: StageContext) -> StageResult:
            return StageResult(next_state=JobState.COMPLETED, message="first")

        async def second(ctx: StageContext) -> StageResult:
            return StageResult(next_state=JobState.COMPLETED, message="second")

        pipeline.register(JobState.PLANNING, first)
        pipeline.register(JobState.PLANNING, second)
        result = asyncio.run(pipeline.step(_ctx(JobState.PLANNING)))
        assert result.message == "second"
