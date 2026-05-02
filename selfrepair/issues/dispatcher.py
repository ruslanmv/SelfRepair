"""Webhook dispatch for Issue Watch.

Two entry points, one per provider, returning a single string status the
webhook route surfaces to the caller (`tracked` / `ignored` / `duplicate`).

Phase-1 contract: webhooks update the `external_issue` row immediately
(state changes, label changes, title edits) so the dashboard reflects
upstream changes without waiting for the next scheduled sync. Comment
events are noted but not stored — comment history lands with Phase-2.

Why a thin dispatcher: the heavy lifting (classify, policy, fingerprint,
upsert) is the same code path the scheduled sync calls. We import
`service._upsert_one` and reuse it, so a behaviour change in the sync
ripples consistently into webhook handling.
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from selfrepair.issues.config import get_runtime
from selfrepair.issues.schemas import ExternalIssueDTO
from selfrepair.issues.service import _upsert_one
from selfrepair.persistence.models import Repo
from selfrepair.persistence.repositories import IssuesRepository

logger = logging.getLogger(__name__)


async def dispatch_github_issue_event(
    *,
    ctx: dict[str, Any],
    event_type: str,
    delivery_id: str,
    payload: dict[str, Any],
) -> str:
    """Route a GitHub `issues` or `issue_comment` webhook event.

    Mutating actions (opened, edited, labeled, unlabeled, reopened, closed)
    upsert the issue. Comment events are acknowledged only.
    """
    runtime = get_runtime()
    if runtime.kill_switch:
        return "ignored"

    if event_type == "issue_comment":
        # Phase-1: acknowledge only. Phase-2 stores the comment.
        return "tracked"

    if event_type != "issues":
        return "ignored"

    issue_payload = payload.get("issue") or {}
    repo_payload = payload.get("repository") or {}
    repo_full_name = repo_payload.get("full_name")
    if not repo_full_name:
        return "ignored"
    if "pull_request" in issue_payload:
        # GitHub re-emits some PR events on the issues channel; skip.
        return "ignored"

    sessionmaker = ctx.get("sessionmaker")
    if sessionmaker is None:
        logger.info("issues dispatcher: no sessionmaker in ctx; logging only")
        return "tracked"

    dto = _github_payload_to_dto(issue_payload, repo_full_name)
    return await _persist_dto(sessionmaker, dto)


async def dispatch_gitlab_issue_event(
    *,
    ctx: dict[str, Any],
    event_type: str,
    payload: dict[str, Any],
) -> str:
    """Route a GitLab `Issue Hook` or `Note Hook` event."""
    runtime = get_runtime()
    if runtime.kill_switch:
        return "ignored"

    if event_type == "Note Hook":
        return "tracked"

    if event_type != "Issue Hook":
        return "ignored"

    project = payload.get("project") or {}
    repo_full_name = project.get("path_with_namespace")
    attrs = payload.get("object_attributes") or {}
    if not repo_full_name or not attrs:
        return "ignored"

    sessionmaker = ctx.get("sessionmaker")
    if sessionmaker is None:
        return "tracked"

    dto = _gitlab_payload_to_dto(payload, repo_full_name)
    return await _persist_dto(sessionmaker, dto)


# ---------------- private helpers ----------------


async def _persist_dto(sessionmaker: Any, dto: ExternalIssueDTO) -> str:
    async with sessionmaker() as session:
        repo = await _resolve_repo(session, dto.provider, dto.repo_full_name)
        if repo is None:
            logger.info(
                "issues dispatcher: unknown repo %s/%s",
                dto.provider, dto.repo_full_name,
            )
            return "ignored"
        issues_repo = IssuesRepository(session)
        await _upsert_one(repo=repo, dto=dto, issues_repo=issues_repo)
        await session.commit()
    return "tracked"


async def _resolve_repo(
    session: Any, provider: str, full_name: str
) -> Repo | None:
    stmt = select(Repo).where(
        Repo.provider == provider, Repo.full_name == full_name
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def _github_payload_to_dto(
    issue: dict[str, Any], repo_full_name: str
) -> ExternalIssueDTO:
    body = issue.get("body") or ""
    return ExternalIssueDTO(
        provider="github",
        provider_issue_id=str(issue.get("node_id") or issue.get("id")),
        repo_full_name=repo_full_name,
        number=int(issue["number"]),
        title=issue.get("title") or "(no title)",
        body_excerpt=body[:2000] if body else None,
        state="closed" if issue.get("state") == "closed" else "open",
        author=(issue.get("user") or {}).get("login"),
        labels=tuple(
            (label.get("name") or "")
            for label in (issue.get("labels") or [])
            if label.get("name")
        ),
        assignees=tuple(
            (a.get("login") or "")
            for a in (issue.get("assignees") or [])
            if a.get("login")
        ),
        html_url=issue.get("html_url"),
        created_at=_iso(issue.get("created_at")),
        updated_at=_iso(issue.get("updated_at")) or datetime.now(UTC),
        closed_at=_iso(issue.get("closed_at")),
        raw=issue,
    )


def _gitlab_payload_to_dto(
    payload: dict[str, Any], repo_full_name: str
) -> ExternalIssueDTO:
    attrs = payload.get("object_attributes") or {}
    user = payload.get("user") or {}
    body = attrs.get("description") or ""
    state = attrs.get("state") or "opened"
    return ExternalIssueDTO(
        provider="gitlab",
        provider_issue_id=str(attrs.get("id")),
        repo_full_name=repo_full_name,
        number=int(attrs.get("iid") or attrs.get("id") or 0) or 1,
        title=attrs.get("title") or "(no title)",
        body_excerpt=body[:2000] if body else None,
        state="closed" if state == "closed" else "open",
        author=user.get("username") or user.get("name"),
        labels=tuple(
            (label.get("title") if isinstance(label, dict) else label) or ""
            for label in (payload.get("labels") or [])
            if label
        ),
        assignees=tuple(
            (a.get("username") or "")
            for a in (payload.get("assignees") or [])
            if a.get("username")
        ),
        html_url=attrs.get("url"),
        created_at=_iso(attrs.get("created_at")),
        updated_at=_iso(attrs.get("updated_at")) or datetime.now(UTC),
        closed_at=_iso(attrs.get("closed_at")),
        raw=payload,
    )


def _iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# Suppress the "unused" lint on uuid; reserved for tests that synthesize ids.
_ = uuid
