"""Issue Watch orchestration.

The service is the only place that knows the order in which the building
blocks must run. Provider clients fetch DTOs, the classifier assigns a
class, the policy decides repairability, the IssuesRepository writes
rows. Tests exercise this at unit level by injecting mock clients +
in-memory repositories.

Design choices:
  * The function takes a `client_factory` so tests don't need to monkey
    patch `clients.build_client`. Production passes the real factory.
  * Reconciliation: issues no longer present in the open-issues page get
    `mark_closed` only when we successfully fetched a non-empty page from
    the provider — a transient empty response must not nuke the dashboard.
  * Errors per repo are isolated; one provider outage doesn't fail the
    whole sync.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from selfrepair.issues.classifier import classify_issue
from selfrepair.issues.clients import IssueProviderClient
from selfrepair.issues.fingerprints import compute_fingerprint
from selfrepair.issues.policies import (
    Repairability,
    decide_repairability,
    derive_priority,
)
from selfrepair.issues.schemas import ExternalIssueDTO
from selfrepair.persistence.models import Repo
from selfrepair.persistence.repositories import IssuesRepository

logger = logging.getLogger(__name__)


ClientFactory = Callable[[str], IssueProviderClient | None]


@dataclass(frozen=True)
class SyncReport:
    """Per-repo summary returned to the worker for log + metrics emission."""

    repo_full_name: str
    provider: str
    upserted: int
    closed_reconciled: int
    errors: int


async def sync_repo_issues(
    *,
    repo: Repo,
    issues_repo: IssuesRepository,
    client_factory: ClientFactory,
) -> SyncReport:
    """Sync one repository's external issues.

    Pipeline (per repo):
      1. Resolve a client via the factory; bail when missing creds.
      2. Fetch open issues from the provider (`list_open_issues`).
      3. For each DTO: classify → decide repairability → upsert row.
      4. Reconcile: any issue we'd seen open before but is missing from
         this fetch gets `mark_closed` — *only* if the fetch was non-empty
         (an empty page may be a transient API hiccup, not a true close).
      5. Always close the client.
    """
    client = client_factory(repo.provider)
    if client is None:
        return SyncReport(
            repo_full_name=repo.full_name,
            provider=repo.provider,
            upserted=0,
            closed_reconciled=0,
            errors=0,
        )

    upserted = 0
    errors = 0
    closed_reconciled = 0

    try:
        try:
            dtos = await client.list_open_issues(repo.full_name)
        except Exception:
            logger.exception(
                "issues sync: list_open_issues failed for %s/%s",
                repo.provider, repo.full_name,
            )
            return SyncReport(
                repo_full_name=repo.full_name,
                provider=repo.provider,
                upserted=0,
                closed_reconciled=0,
                errors=1,
            )

        seen_provider_ids: set[str] = set()
        for dto in dtos:
            try:
                await _upsert_one(
                    repo=repo, dto=dto, issues_repo=issues_repo
                )
                seen_provider_ids.add(dto.provider_issue_id)
                upserted += 1
            except Exception:
                logger.exception(
                    "issues sync: upsert failed for %s#%s",
                    dto.repo_full_name, dto.number,
                )
                errors += 1

        # Reconciliation. Skipped on empty response — one transient empty
        # page from a provider outage must not flip every issue to closed.
        if dtos:
            closed_reconciled = await _reconcile_closed(
                repo=repo,
                issues_repo=issues_repo,
                seen_provider_ids=seen_provider_ids,
            )
    finally:
        await client.aclose()

    return SyncReport(
        repo_full_name=repo.full_name,
        provider=repo.provider,
        upserted=upserted,
        closed_reconciled=closed_reconciled,
        errors=errors,
    )


async def _upsert_one(
    *,
    repo: Repo,
    dto: ExternalIssueDTO,
    issues_repo: IssuesRepository,
) -> None:
    classification = classify_issue(dto)
    decision = decide_repairability(dto, classification)
    repairable = decision.repairability is not Repairability.ESCALATE
    fingerprint = compute_fingerprint(
        repo_full_name=dto.repo_full_name,
        title=dto.title,
        provider_issue_id=dto.provider_issue_id,
    )
    await issues_repo.upsert_issue(
        org_id=repo.org_id,
        repo_id=repo.id,
        provider=dto.provider,
        provider_issue_id=dto.provider_issue_id,
        number=dto.number,
        title=dto.title,
        body_excerpt=dto.body_excerpt,
        state=dto.state,
        author=dto.author,
        labels=list(dto.labels),
        assignees=list(dto.assignees),
        priority=derive_priority(dto),
        repair_class=classification.cls.value,
        repairable=repairable,
        html_url=dto.html_url,
        created_at_external=dto.created_at,
        updated_at_external=dto.updated_at,
        closed_at_external=dto.closed_at,
        raw=dto.raw,
        fingerprint=fingerprint,
    )


async def _reconcile_closed(
    *,
    repo: Repo,
    issues_repo: IssuesRepository,
    seen_provider_ids: Iterable[str],
) -> int:
    """Mark any open row we didn't see in this sync as closed.

    The repository carries the existing rows. We list `state=open` rows
    for this repo and mark any whose provider_issue_id isn't in
    seen_provider_ids as closed.
    """
    seen_set = set(seen_provider_ids)
    existing = await issues_repo.list_issues(
        org_id=repo.org_id,
        repo_id=repo.id,
        state="open",
        limit=500,
    )
    closed = 0
    for row in existing:
        if row.provider != repo.provider:
            continue  # don't reconcile across providers
        if row.provider_issue_id in seen_set:
            continue
        await issues_repo.mark_closed(row.id)
        closed += 1
    return closed
