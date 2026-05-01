from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

RepairMode = Literal["dry_run", "suggest", "apply_local", "branch", "pull_request", "safe"]


class RepoRequest(BaseModel):
    """Request to scan and optionally repair a repository.

    The API defaults to dry-run behavior. `safe` is accepted for backward
    compatibility and is treated as `dry_run` unless DRY_RUN=false is set.
    """

    repo_url: HttpUrl | str = Field(..., description="Git clone URL or HTTPS repository URL")
    branch: str = Field(default="main", min_length=1, max_length=128)
    repair_mode: RepairMode = Field(default="dry_run")
