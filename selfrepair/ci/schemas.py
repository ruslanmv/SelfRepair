"""Pydantic models for incoming GitHub Actions webhook payloads.

Intentionally narrow: just the fields the dispatcher actually needs. The
original payload is kept as `raw` jsonb on the row so we can add fields
later without re-shipping migrations.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class _GitHubRepository(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    full_name: str


class _GitHubInstallation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int


class _WorkflowRun(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    workflow_id: int
    name: str | None = None
    path: str | None = None
    head_sha: str | None = None
    head_branch: str | None = None
    event: str | None = None
    status: str | None = None
    conclusion: str | None = None
    run_attempt: int | None = None
    html_url: str | None = None
    run_started_at: datetime | None = None
    updated_at: datetime | None = None


class WorkflowRunEvent(BaseModel):
    """Subset of a `workflow_run` webhook payload."""

    model_config = ConfigDict(extra="ignore")
    action: str
    workflow_run: _WorkflowRun
    repository: _GitHubRepository
    installation: _GitHubInstallation | None = None


class _WorkflowJobStep(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str | None = None
    status: str | None = None
    conclusion: str | None = None
    number: int | None = None


class _WorkflowJob(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int
    run_id: int
    name: str | None = None
    status: str | None = None
    conclusion: str | None = None
    runner_name: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    steps: list[_WorkflowJobStep] = Field(default_factory=list)


class WorkflowJobEvent(BaseModel):
    """Subset of a `workflow_job` webhook payload."""

    model_config = ConfigDict(extra="ignore")
    action: str
    workflow_job: _WorkflowJob
    repository: _GitHubRepository
    installation: _GitHubInstallation | None = None
