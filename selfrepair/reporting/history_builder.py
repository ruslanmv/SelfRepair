from __future__ import annotations

import json
from pathlib import Path

from selfrepair.models import RepoHealthReport


def write_history(path: Path, reports: list[RepoHealthReport]) -> None:
    items = [report.model_dump(mode="json") for report in reports]
    path.write_text(json.dumps({"items": items}, indent=2), encoding="utf-8")
