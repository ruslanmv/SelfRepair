from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from selfrepair.metrics.dashboard import compute_dashboard_metrics


def _scalar_stub(*values):
    """Build an AsyncMock that returns a Result whose `.scalar()` walks `values`.

    Each call to `session.execute(...)` returns a fresh Result; we use this
    to script the sequence of count/avg queries the dashboard issues.
    """
    iterator = iter(values)

    async def execute(_stmt):
        result = MagicMock()
        result.scalar = MagicMock(return_value=next(iterator))
        return result

    return execute


class TestDashboardMetrics:
    @pytest.mark.asyncio
    async def test_zero_state(self) -> None:
        session = MagicMock()
        # merged_count, failed_count, reverted_count, mttr, avg_cost
        session.execute = AsyncMock(side_effect=_scalar_stub(0, 0, 0, None, None))
        metrics = await compute_dashboard_metrics(session)
        assert metrics.auto_fix_success_rate == 0.0
        assert metrics.mttr_seconds_avg is None
        assert metrics.usd_per_repair_avg == 0.0
        assert metrics.regression_rate == 0.0
        assert metrics.sample_size == 0

    @pytest.mark.asyncio
    async def test_basic_aggregates(self) -> None:
        session = MagicMock()
        # 8 merged, 2 failed (incl 1 reverted), MTTR 3600s, $0.05 avg
        session.execute = AsyncMock(
            side_effect=_scalar_stub(8, 2, 1, 3600.0, 0.05)
        )
        metrics = await compute_dashboard_metrics(session)
        assert metrics.auto_fix_success_rate == 0.8
        assert metrics.mttr_seconds_avg == 3600.0
        assert metrics.usd_per_repair_avg == 0.05
        # 1 reverted / (8 merged + 1 reverted) = 1/9
        assert round(metrics.regression_rate, 4) == round(1 / 9, 4)
        assert metrics.sample_size == 10

    @pytest.mark.asyncio
    async def test_perfect_success(self) -> None:
        session = MagicMock()
        # 10 merged, 0 failed, 0 reverted
        session.execute = AsyncMock(
            side_effect=_scalar_stub(10, 0, 0, 1800.0, 0.02)
        )
        metrics = await compute_dashboard_metrics(session)
        assert metrics.auto_fix_success_rate == 1.0
        assert metrics.regression_rate == 0.0
        assert metrics.sample_size == 10
