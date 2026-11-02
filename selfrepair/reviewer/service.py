"""Run one review: diff, engines, validation, policy, publication.

The configured engine may be Deep Agents. The deterministic engine always
runs as well, and its findings cannot be discarded by an empty model report.
A missing diff or an unavailable model finishes as `action_required`, never
as a successful check.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

from selfrepair.config.repo_config import ReviewerConfig
from selfrepair.policy.glob import matches
from selfrepair.reviewer.diff import limit_diff
from selfrepair.reviewer.engines.deterministic import DeterministicReviewEngine
from selfrepair.reviewer.policy import conclude
from selfrepair.reviewer.publishers import Publisher
from selfrepair.reviewer.schemas import (
    ZERO_SHA,
    DiffFile,
    DiffSet,
    EngineUnavailable,
    FindingDraft,
    RepoBinding,
    ReviewEvent,
    ReviewReport,
    RunRecord,
    TransientReviewError,
)
from selfrepair.reviewer.store import ReviewStore
from selfrepair.reviewer.validator import validate_findings


class DiffProvider(Protocol):
    """Fetches the patch for an event. Must not execute repository code."""

    async def collect(self, event: ReviewEvent, repo: RepoBinding) -> DiffSet: ...


class StaticDiffProvider:
    """Returns a prepared diff. Tests and callers that already have a patch use this."""

    def __init__(self, files: list[DiffFile] | None = None, *, error: str | None = None) -> None:
        self._files = list(files or [])
        self._error = error

    async def collect(self, event: ReviewEvent, repo: RepoBinding) -> DiffSet:
        del event, repo
        if self._error:
            return DiffSet(source="unavailable", error=self._error)
        limited = limit_diff(self._files)
        limited.source = "static"
        return limited


def branch_allowed(config: ReviewerConfig, event: ReviewEvent) -> bool:
    """Pushes match the pushed branch. Reviews match the target branch."""
    if event.deleted:
        return True
    name = event.branch if event.kind == "push" else (event.base_branch or event.branch)
    if any(_branch_match(name, pattern) for pattern in config.branches.exclude):
        return False
    if not config.branches.include:
        return True
    return any(_branch_match(name, pattern) for pattern in config.branches.include)


def trigger_allowed(config: ReviewerConfig, event: ReviewEvent) -> bool:
    """Return True when this event family is enabled."""
    if event.kind == "push":
        return config.triggers.push
    if event.kind == "pull_request":
        return config.triggers.pull_request
    return config.triggers.merge_request


async def review_change(
    *,
    store: ReviewStore,
    repo: RepoBinding,
    event: ReviewEvent,
    config: ReviewerConfig,
    diff_provider: DiffProvider,
    engine: Any,
    publisher: Publisher,
    job_try: int = 1,
) -> tuple[str, RunRecord | None]:
    """Create or reuse one run for the change set and publish its result.

    Returns `(outcome, run)`. Outcome is `reviewed`, `duplicate`, `ignored`,
    or `incomplete`.
    """
    if not config.enabled or not trigger_allowed(config, event):
        return "ignored", None
    if not branch_allowed(config, event):
        return "ignored", None
    if event.draft and event.action != "ready_for_review":
        return "ignored", None

    claimed = await store.claim_delivery(provider=event.provider, delivery_id=event.delivery_id)
    if not claimed and job_try <= 1:
        existing = await store.get_run_by_key(
            org_id=repo.org_id,
            repo_id=repo.repo_id,
            head_sha=event.head_sha,
            base_sha=event.base_sha,
            policy_version=config.policy_version,
        )
        return "duplicate", existing

    if event.deleted or event.head_sha == ZERO_SHA:
        run = await _ensure_run(store, repo, event, config, status="skipped")
        run = await store.update_run(
            run.id,
            status="skipped",
            conclusion="neutral",
            summary="Branch deleted. No diff was analyzed.",
            completed_at=_now(),
        )
        return "reviewed", run

    run = await _ensure_run(store, repo, event, config, status="running")
    if event.installation_id is not None:
        await store.remember_installation(
            repo_id=repo.repo_id, installation_id=event.installation_id
        )
    try:
        announce = getattr(publisher, "announce", None)
        if announce is not None:
            await announce(event=event, run=run)
        diff = await diff_provider.collect(event, repo)
        report = _run_engines(event, diff, config, engine)
        validated = validate_findings(diff, report.findings) if diff.files else []
        incomplete = report.incomplete_reason or diff.error
        conclusion = conclude(
            config,
            validated,
            incomplete_reason=incomplete,
            truncated=diff.truncated,
        )
        status = "incomplete" if incomplete and conclusion != "failure" else "completed"
        if diff.truncated and conclusion == "action_required":
            status = "completed"
        summary = _summary(event, report, conclusion, diff)
        await store.add_findings(run.id, validated)
        already = await store.published_fingerprints(
            repo_id=repo.repo_id, pr_number=event.pr_number
        )
        publications = await publisher.publish(
            event=event,
            run=run,
            findings=validated,
            conclusion=conclusion,
            summary=summary,
            already_published=already,
        )
        publication_errors = [
            str(item.get("error") or item.get("status"))
            for item in publications
            if item.get("status") in {"failed", "unpublished"}
        ]
        if publication_errors and conclusion == "success":
            conclusion = "action_required"
            incomplete = incomplete or "publication failed"
            status = "incomplete"
            summary = f"{summary}\nPublication failed. This check was not sent."
        for item in publications:
            await store.add_publication(
                org_id=repo.org_id,
                run_id=run.id,
                provider=event.provider,
                kind=item["kind"],
                status=_publication_status(item.get("status")),
                external_id=item.get("external_id"),
                fingerprints=item.get("fingerprints") or [],
                payload=item.get("body") or {},
                error=item.get("error"),
            )
        await store.supersede_ref(repo_id=repo.repo_id, ref=event.ref, except_run_id=run.id)
        run = await store.update_run(
            run.id,
            status=status,
            conclusion=conclusion,
            summary=summary,
            engine=report.engine,
            model_id=report.model_id,
            error=incomplete or ("; ".join(publication_errors) or None),
            completed_at=_now(),
        )
        return ("reviewed" if status == "completed" else "incomplete"), run
    except TransientReviewError:
        await store.update_run(run.id, status="queued", conclusion=None, error="transient")
        raise
    except Exception as exc:  # noqa: BLE001 — a review must not end as success
        run = await store.update_run(
            run.id,
            status="incomplete",
            conclusion="action_required",
            summary="Review failed before a trustworthy result was produced.",
            error=type(exc).__name__,
            completed_at=_now(),
        )
        return "incomplete", run


def _run_engines(
    event: ReviewEvent,
    diff: DiffSet,
    config: ReviewerConfig,
    engine: Any,
) -> ReviewReport:
    deterministic = DeterministicReviewEngine().review(event, diff, config)
    missing = not diff.files and event.base_sha != event.head_sha
    if missing or (diff.error and not diff.files):
        return ReviewReport(
            summary=deterministic.summary,
            findings=deterministic.findings,
            engine="deterministic",
            incomplete_reason=diff.error or "diff unavailable",
        )
    if not diff.files:
        return deterministic
    if getattr(engine, "name", "deterministic") == "deterministic":
        return deterministic
    try:
        model_report = engine.review(event, diff, config)
    except EngineUnavailable as exc:
        return ReviewReport(
            summary=f"{deterministic.summary} Deep Agents unavailable: {exc.reason}",
            findings=deterministic.findings,
            engine="deterministic",
            model_id=None,
            incomplete_reason=exc.reason,
        )
    merged: list[FindingDraft] = list(deterministic.findings)
    merged.extend(model_report.findings)
    reason = model_report.incomplete_reason
    if diff.truncated:
        reason = reason or "diff truncated"
    return ReviewReport(
        summary=model_report.summary or deterministic.summary,
        findings=merged,
        engine=model_report.engine,
        model_id=model_report.model_id,
        incomplete_reason=reason,
    )


async def _ensure_run(
    store: ReviewStore,
    repo: RepoBinding,
    event: ReviewEvent,
    config: ReviewerConfig,
    *,
    status: str,
) -> RunRecord:
    existing = await store.get_run_by_key(
        org_id=repo.org_id,
        repo_id=repo.repo_id,
        head_sha=event.head_sha,
        base_sha=event.base_sha,
        policy_version=config.policy_version,
    )
    if existing is not None:
        return existing
    record = RunRecord(
        id=uuid.uuid4(),
        org_id=repo.org_id,
        repo_id=repo.repo_id,
        provider=event.provider,
        event_type=event.kind,
        delivery_id=event.delivery_id,
        ref=event.ref,
        pr_number=event.pr_number,
        base_sha=event.base_sha,
        head_sha=event.head_sha,
        forced=event.forced,
        from_fork=event.from_fork,
        engine=config.engine,
        policy_version=config.policy_version,
        status=status,
        sender_login=event.sender_login,
        commit_shas=[item.sha for item in event.commits],
        metadata={
            "action": event.action,
            "branch": event.branch,
            "base_branch": event.base_branch,
            "project_id": event.project_id,
            "installation_id": event.installation_id,
            "repo_full_name": event.repo_full_name,
        },
        started_at=_now(),
    )
    return await store.insert_run(record)


def _summary(event: ReviewEvent, report: ReviewReport, conclusion: str, diff: DiffSet) -> str:
    commits = ", ".join(item.sha[:8] for item in event.commits[:10]) or event.head_sha[:12]
    parts = [
        f"Repository: {event.repo_full_name}",
        f"Branch: {event.branch}",
        f"Range: {event.base_sha[:12]}..{event.head_sha[:12]}",
        f"Commits: {commits}",
        f"Conclusion: {conclusion}",
        f"Engine: {report.engine}",
        "",
        report.summary,
    ]
    if diff.truncated:
        parts.append("The diff was truncated. This check does not pass on the unread portion.")
    if report.incomplete_reason:
        parts.append(f"Incomplete: {report.incomplete_reason}")
    return "\n".join(parts)


def _branch_match(name: str, pattern: str) -> bool:
    if any(token in pattern for token in "*?["):
        return matches(name, pattern)
    return name == pattern


def _publication_status(raw: Any) -> str:
    if raw in {"published", "recorded", "failed", "unpublished"}:
        return str(raw)
    return "failed"


def _now() -> datetime:
    return datetime.now(UTC)
