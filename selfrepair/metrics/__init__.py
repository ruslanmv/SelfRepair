"""Product metrics that matter (design §9).

Four numbers a platform team will benchmark you on:
  - auto_fix_success_rate
  - mttr_seconds_avg
  - usd_per_repair_avg
  - regression_rate

Exposed at GET /v1/metrics/dashboard. Each is a simple aggregate over the
repair table; we deliberately avoid invented composites so the numbers are
re-derivable from the audit log.
"""
from selfrepair.metrics.dashboard import (
    DashboardMetrics,
    compute_dashboard_metrics,
)

__all__ = ["DashboardMetrics", "compute_dashboard_metrics"]
