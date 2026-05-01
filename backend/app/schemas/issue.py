from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Severity = Literal["info", "low", "medium", "high", "critical"]
Category = Literal["delivery", "quality", "security", "documentation", "runtime", "compliance"]


class Issue(BaseModel):
    title: str
    category: Category = "delivery"
    severity: Severity = "medium"
    description: str
    check_name: str | None = None
    recommendation: str | None = None
