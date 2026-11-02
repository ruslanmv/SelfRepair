"""Webhook entry point for code review.

Push and pull-request events arrive from `ingest_webhook`. GitLab merge
requests arrive from `ingest_gitlab_webhook`. Unknown repositories, disabled
monitoring, deleted branches' analysis, and SelfRepair's own repair branches
do not start a model call.
"""
from __future__ import annotations

import logging
from typing import Any

from selfrepair.reviewer.engines.deterministic import DeterministicReviewEngine
from selfrepair.reviewer.events import (
    EventRejected,
    github_event,
    gitlab_merge_request,
    recursion_risk,
)
from selfrepair.reviewer.publishers import RecordingPublisher
from selfrepair.reviewer.schemas import TransientReviewError
from selfrepair.reviewer.service import review_change
from selfrepair.reviewer.settings import resolve_reviewer_config
from selfrepair.reviewer.store import ReviewStore, SqlReviewStore

logger = logging.getLogger(__name__)

_GITHUB_REVIEW_EVENTS = frozenset({"push", "pull_request"})


def store_from_ctx(ctx: dict[str, Any]) -> ReviewStore | None:
    """Prefer an injected store. Otherwise build the SQL store from the worker session."""
    injected = ctx.get("review_store")
    if injected is not None:
        return injected
    sessionmaker = ctx.get("sessionmaker")
    if sessionmaker is None:
        return None
    return SqlReviewStore(sessionmaker)


async def dispatch_github_review_event(
    *,
    ctx: dict[str, Any],
    event_type: str,
    delivery_id: str,
    payload: dict[str, Any],
) -> str:
    """Handle a GitHub push or pull_request webhook. Other events return `ignored`."""
    if event_type not in _GITHUB_REVIEW_EVENTS:
        return "ignored"
    try:
        event = github_event(event_type, delivery_id, payload)
    except EventRejected as exc:
        logger.info("review ignored reason=%s delivery=%s", exc.reason, delivery_id)
        return "ignored"
    return await _dispatch(ctx, event)


async def dispatch_gitlab_review_event(
    *,
    ctx: dict[str, Any],
    event_type: str,
    payload: dict[str, Any],
    delivery_id: str | None = None,
) -> str:
    """Handle a GitLab Merge Request Hook. Issue hooks stay with Issue Watch."""
    if event_type != "Merge Request Hook":
        return "ignored"
    digest = delivery_id or _gitlab_delivery_id(payload)
    try:
        event = gitlab_merge_request(digest, payload)
    except EventRejected as exc:
        logger.info("gitlab review ignored reason=%s", exc.reason)
        return "ignored"
    return await _dispatch(ctx, event)


async def _dispatch(ctx: dict[str, Any], event: Any) -> str:
    if recursion_risk(event):
        logger.info(
            "review skipped recursion guard repo=%s branch=%s",
            event.repo_full_name,
            event.branch,
        )
        return "ignored"
    store = store_from_ctx(ctx)
    if store is None:
        logger.info(
            "review event accepted but no store is configured repo=%s",
            event.repo_full_name,
        )
        return "tracked"
    repo = await store.resolve_repo(
        provider=event.provider,
        full_name=event.repo_full_name,
        installation_id=event.installation_id,
    )
    if repo is None or repo.ambiguous:
        logger.info("review ignored unknown or ambiguous repo=%s", event.repo_full_name)
        return "ignored"
    org_settings, repo_settings = await store.settings_for(
        org_id=repo.org_id, repo_id=repo.repo_id
    )
    config = resolve_reviewer_config(
        config_yaml=repo.config_yaml,
        org_settings=org_settings,
        repo_settings=repo_settings,
    )
    engine = ctx.get("review_engine")
    if engine is None and config.engine == "deepagents":
        from selfrepair.reviewer.engines.deepagents_engine import DeepAgentsReviewEngine

        engine = DeepAgentsReviewEngine()
    if engine is None:
        engine = DeterministicReviewEngine()
    provider = ctx.get("diff_provider")
    if provider is None:
        from selfrepair.reviewer.diff_provider import provider_from_env

        provider = provider_from_env()
    publisher = ctx.get("review_publisher") or RecordingPublisher()
    job_try = int(ctx.get("job_try") or 1)
    try:
        outcome, _run = await review_change(
            store=store,
            repo=repo,
            event=event,
            config=config,
            diff_provider=provider,
            engine=engine,
            publisher=publisher,
            job_try=job_try,
        )
    except TransientReviewError:
        logger.warning("review transient failure delivery=%s", event.delivery_id)
        raise
    return outcome


def _gitlab_delivery_id(payload: dict[str, Any]) -> str:
    attrs = payload.get("object_attributes") or {}
    return f"gitlab-mr:{attrs.get('id')}:{attrs.get('action')}:{attrs.get('last_commit', {}).get('id', '')}"
