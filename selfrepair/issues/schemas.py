"""Provider-neutral DTOs for the Issue Watch pipeline.

The wire shape that crosses the package boundary. Provider clients map
their JSON to ExternalIssueDTO; the service consumes that DTO and never
needs to know whether an issue came from GitHub, GitLab, or HuggingFace.

Pydantic with `extra="ignore"` so a provider adding a new field never
breaks us; the original payload is forwarded as `raw` for the audit row.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Provider = Literal["github", "gitlab", "huggingface"]
IssueState = Literal["open", "closed"]


class ExternalIssueDTO(BaseModel):
    """One human-created issue, normalised across providers.

    `provider_issue_id` is the provider's stable id (GitHub node_id, GitLab
    numeric id, HF discussion num+repo). `number` is the human-visible
    integer that appears in URLs.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    provider: Provider
    provider_issue_id: str = Field(min_length=1, max_length=128)
    repo_full_name: str = Field(min_length=1, max_length=255)
    number: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=500)
    body_excerpt: str | None = Field(default=None, max_length=2000)
    state: IssueState = "open"
    author: str | None = Field(default=None, max_length=255)
    labels: tuple[str, ...] = ()
    assignees: tuple[str, ...] = ()
    html_url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    closed_at: datetime | None = None
    raw: dict[str, Any] | None = None


class IssueComment(BaseModel):
    """Single comment under an external issue. Reserved for Phase-2
    offline comment history — not used by the Phase-1 sync."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    provider: Provider
    provider_comment_id: str
    author: str | None = None
    body_excerpt: str | None = Field(default=None, max_length=2000)
    html_url: str | None = None
    created_at: datetime | None = None
    raw: dict[str, Any] | None = None
