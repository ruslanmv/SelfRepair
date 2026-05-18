"""`/v1/dashboard` — single aggregate endpoint for the Overview surface.

Returns the exact shape `Overview.jsx` consumes:

```
{
  "kpis": { repos_total, open_findings, auto_fix_success_rate,
            mttr_seconds_avg, monthly_spend_usd, ... },
  "fleet_health": [ { band, count }, ... ],
  "repair_cost":   { spend_usd, month_label, ... },
  "activity":      [ { ts, message, stage, repo_full_name }, ... ],
  "awaiting_approval": [ { repair_id, repo, finding }, ... ]
}
```

One aggregate request keeps the dashboard's first paint fast and lets
the SPA render the screen in a single React-Query call rather than
orchestrating four concurrent ones.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from selfrepair.api.deps import CtxDep, SessionDep
from selfrepair.persistence.repositories.dashboard import DashboardRepository

router = APIRouter(prefix="/v1/dashboard", tags=["dashboard"])


@router.get("")
async def get_dashboard(ctx: CtxDep, session: SessionDep) -> dict[str, Any]:
    return await DashboardRepository(session).compute(ctx.org_id)
