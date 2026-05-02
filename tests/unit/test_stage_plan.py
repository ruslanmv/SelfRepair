from __future__ import annotations

import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from selfrepair.config.repo_config import RepoConfig
from selfrepair.sdk.models import Finding, Severity
from selfrepair.state.machine import JobState
from selfrepair.worker.pipeline import StageContext
from selfrepair.worker.stages.plan import plan_stage


@dataclass
class _StubRepo:
    id: uuid.UUID
    full_name: str = "agent-matrix/demo"
    default_branch: str = "main"


def _stage_ctx(
    *,
    findings: list[Finding] | None = None,
    repo_config: RepoConfig | None = None,
) -> StageContext:
    repo = _StubRepo(id=uuid.uuid4())
    session = MagicMock()
    # ReposRepository(session).get(repo_id) -> repo
    session_get = AsyncMock(return_value=repo)
    session.get = session_get
    return StageContext(
        job_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        repo_id=repo.id,
        state=JobState.PLANNING,
        session=session,  # type: ignore[arg-type]
        extra={
            "scanned_findings": findings or [],
            "repo_config": repo_config,
        },
    )


class TestPlanStage:
    @pytest.mark.asyncio
    async def test_short_circuits_to_completed_with_no_findings(self) -> None:
        result = await plan_stage(_stage_ctx(findings=[]))
        assert result.next_state == JobState.COMPLETED
        assert result.payload == {"plans": 0}

    @pytest.mark.asyncio
    async def test_skips_findings_without_a_fixer(self, tmp_path) -> None:
        finding = Finding(
            kind="unknown_kind",
            severity=Severity.LOW,
            file_path="x.py",
        )
        ctx = _stage_ctx(findings=[finding])
        result = await plan_stage(ctx)
        # No plans → COMPLETED, with the finding in skipped
        assert result.next_state == JobState.COMPLETED
        skipped = result.payload["skipped"]
        assert len(skipped) == 1
        assert skipped[0]["reason"] == "no fixer"

    @pytest.mark.asyncio
    async def test_builds_plans_for_known_findings(self) -> None:
        finding = Finding(
            kind="makefile_missing",
            severity=Severity.LOW,
            file_path="Makefile",
        )
        # default RepoConfig has codeowners_required=True, which produces a
        # REVIEW outcome — still ALLOW-equivalent for plan creation.
        result = await plan_stage(_stage_ctx(findings=[finding]))
        assert result.next_state == JobState.REPAIRING
        assert result.payload["plans"] == 1

    @pytest.mark.asyncio
    async def test_drops_findings_denied_by_policy(self) -> None:
        finding = Finding(
            kind="makefile_missing",
            severity=Severity.LOW,
            file_path="Makefile",
        )
        # deny_paths matches Makefile → policy says DENY → plan dropped
        config = RepoConfig.model_validate(
            {"version": 1, "deny_paths": ["Makefile"]}
        )
        result = await plan_stage(
            _stage_ctx(findings=[finding], repo_config=config)
        )
        assert result.next_state == JobState.COMPLETED
        skipped = result.payload["skipped"]
        assert any(
            "deny_paths" in s.get("reason", "") for s in skipped
        )
