"""Dispatcher de-dup, kill switch, and DB write contracts.

The dispatcher is the only path from a webhook to a workflow_run row, so:
  * kill switch is honoured before anything else
  * delivery_id is claimed exactly once
  * a workflow_run row is upserted on a workflow_run event
  * unknown repos are dropped (no row), not crashed on
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("selfrepair")
pytest.importorskip("pydantic")

from selfrepair.ci import dispatcher  # noqa: E402
from selfrepair.ci.config import CIGuardianRuntime  # noqa: E402


def _runtime(*, kill: bool = False) -> CIGuardianRuntime:
    return CIGuardianRuntime(
        kill_switch=kill,
        redis_dedupe_ttl_seconds=86400,
        storm_window_seconds=60,
        storm_threshold=10,
    )


def _wf_run_payload() -> dict[str, Any]:
    return {
        "action": "completed",
        "workflow_run": {
            "id": 12345,
            "workflow_id": 7,
            "name": "CI",
            "path": ".github/workflows/ci.yml",
            "head_sha": "abc",
            "head_branch": "main",
            "event": "push",
            "status": "completed",
            "conclusion": "failure",
            "run_attempt": 1,
            "html_url": "https://github.com/octo/x/actions/runs/12345",
        },
        "repository": {"id": 1, "full_name": "octo/x"},
    }


class TestKillSwitch:
    @pytest.mark.asyncio
    async def test_kill_switch_drops_event_before_anything_else(self) -> None:
        with patch.object(dispatcher, "get_runtime", return_value=_runtime(kill=True)):
            out = await dispatcher.dispatch_ci_event(
                ctx={},
                event_type="workflow_run",
                delivery_id="deliv-1",
                payload=_wf_run_payload(),
            )
        assert out == "ignored"


class TestDeliveryDedupe:
    @pytest.mark.asyncio
    async def test_redis_setnx_failure_to_claim_returns_duplicate(self) -> None:
        redis = MagicMock()
        redis.set = AsyncMock(return_value=None)  # NX failed → already claimed
        with patch.object(dispatcher, "get_runtime", return_value=_runtime()):
            out = await dispatcher.dispatch_ci_event(
                ctx={"redis": redis},
                event_type="workflow_run",
                delivery_id="deliv-1",
                payload=_wf_run_payload(),
            )
        assert out == "duplicate"
        redis.set.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_redis_falls_through_to_handler(self) -> None:
        # Without a sessionmaker, the handler still returns "tracked".
        with patch.object(dispatcher, "get_runtime", return_value=_runtime()):
            out = await dispatcher.dispatch_ci_event(
                ctx={},
                event_type="workflow_run",
                delivery_id="deliv-1",
                payload=_wf_run_payload(),
            )
        assert out == "tracked"


class TestPayloadValidation:
    @pytest.mark.asyncio
    async def test_invalid_payload_is_ignored(self) -> None:
        with patch.object(dispatcher, "get_runtime", return_value=_runtime()):
            out = await dispatcher.dispatch_ci_event(
                ctx={},
                event_type="workflow_run",
                delivery_id="deliv-x",
                payload={"action": "completed"},  # missing workflow_run + repo
            )
        assert out == "ignored"

    @pytest.mark.asyncio
    async def test_missing_repo_fullname_is_ignored(self) -> None:
        with patch.object(dispatcher, "get_runtime", return_value=_runtime()):
            out = await dispatcher.dispatch_ci_event(
                ctx={},
                event_type="workflow_run",
                delivery_id="deliv-x",
                payload={"action": "completed", "workflow_run": {}, "repository": {}},
            )
        assert out == "ignored"


class TestUnhandledEventTypes:
    @pytest.mark.asyncio
    async def test_check_run_is_acknowledged_only(self) -> None:
        # Phase 5 wires Checks API; phase 1 just acknowledges.
        with patch.object(dispatcher, "get_runtime", return_value=_runtime()):
            out = await dispatcher.dispatch_ci_event(
                ctx={},
                event_type="check_run",
                delivery_id="deliv-cr",
                payload={"repository": {"full_name": "octo/x"}},
            )
        assert out == "tracked"


class TestSessionWiring:
    @pytest.mark.asyncio
    async def test_unknown_repo_is_logged_but_not_persisted(self) -> None:
        # Sessionmaker yields an AsyncSession-like mock whose execute()
        # returns a result that scalar_one_or_none() → None.
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=None)
        session = MagicMock()
        session.execute = AsyncMock(return_value=result)
        session.commit = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        sessionmaker = MagicMock(return_value=session)

        with patch.object(dispatcher, "get_runtime", return_value=_runtime()):
            out = await dispatcher.dispatch_ci_event(
                ctx={"sessionmaker": sessionmaker},
                event_type="workflow_run",
                delivery_id="deliv-unknown",
                payload=_wf_run_payload(),
            )
        assert out == "ignored"
        session.commit.assert_not_awaited()
