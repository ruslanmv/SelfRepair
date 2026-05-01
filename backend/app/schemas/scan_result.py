from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.schemas.issue import Issue


class ScanResult(BaseModel):
    repo: str
    repo_path: str | None = None
    repo_type: str = "unknown"
    platform: str = "github"
    checks: dict[str, bool] = Field(default_factory=dict)
    issues: list[Issue] = Field(default_factory=list)
    issues_found: int = 0
    health_score_before: int = 0
