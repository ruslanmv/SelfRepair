"""Review persistence.

`MemoryReviewStore` is the store unit tests use. `SqlReviewStore` is what the
worker uses when a sessionmaker is in the Arq context. Both speak in
`RunRecord` values so the service does not touch ORM rows.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from selfrepair.persistence.models import Repo
from selfrepair.persistence.review_models import (
    ReviewDelivery,
    ReviewFinding,
    ReviewPublication,
    ReviewRun,
    ReviewSettingsRow,
)
from selfrepair.reviewer.schemas import FindingRecord, RepoBinding, RunRecord


class ReviewStore(Protocol):
    """The operations the dispatcher and the API need."""

    async def claim_delivery(self, *, provider: str, delivery_id: str) -> bool: ...

    async def resolve_repo(
        self,
        *,
        provider: str,
        full_name: str,
        installation_id: int | None,
    ) -> RepoBinding | None: ...

    async def settings_for(
        self, *, org_id: uuid.UUID, repo_id: uuid.UUID
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]: ...

    async def put_settings(
        self,
        *,
        org_id: uuid.UUID,
        repo_id: uuid.UUID | None,
        config: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def get_run_by_key(
        self,
        *,
        org_id: uuid.UUID,
        repo_id: uuid.UUID,
        head_sha: str,
        base_sha: str,
        policy_version: str,
    ) -> RunRecord | None: ...

    async def get_run(self, run_id: uuid.UUID) -> RunRecord | None: ...

    async def insert_run(self, record: RunRecord) -> RunRecord: ...

    async def update_run(self, run_id: uuid.UUID, **fields: Any) -> RunRecord: ...

    async def add_findings(self, run_id: uuid.UUID, findings: list[FindingRecord]) -> None: ...

    async def list_findings(self, run_id: uuid.UUID) -> list[FindingRecord]: ...

    async def supersede_ref(
        self, *, repo_id: uuid.UUID, ref: str | None, except_run_id: uuid.UUID
    ) -> int: ...

    async def published_fingerprints(
        self, *, repo_id: uuid.UUID, pr_number: int | None
    ) -> set[str]: ...

    async def add_publication(
        self,
        *,
        org_id: uuid.UUID,
        run_id: uuid.UUID,
        provider: str,
        kind: str,
        status: str,
        external_id: str | None,
        fingerprints: list[str],
        payload: dict[str, Any],
        error: str | None = None,
    ) -> None: ...

    async def list_runs(
        self,
        *,
        org_id: uuid.UUID,
        repo_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[RunRecord]: ...

    async def remember_installation(
        self, *, repo_id: uuid.UUID, installation_id: int
    ) -> None: ...


def _now() -> datetime:
    return datetime.now(UTC)


class MemoryReviewStore:
    """Process-local store. Sufficient for dispatcher tests and local dry runs."""

    def __init__(self, repos: list[RepoBinding] | None = None) -> None:
        self.repos = list(repos or [])
        self.deliveries: set[tuple[str, str]] = set()
        self.runs: dict[uuid.UUID, RunRecord] = {}
        self.findings: dict[uuid.UUID, list[FindingRecord]] = {}
        self.publications: list[dict[str, Any]] = []
        self.org_settings: dict[uuid.UUID, dict[str, Any]] = {}
        self.repo_settings: dict[tuple[uuid.UUID, uuid.UUID], dict[str, Any]] = {}

    async def claim_delivery(self, *, provider: str, delivery_id: str) -> bool:
        key = (provider, delivery_id)
        if key in self.deliveries:
            return False
        self.deliveries.add(key)
        return True

    async def resolve_repo(
        self,
        *,
        provider: str,
        full_name: str,
        installation_id: int | None,
    ) -> RepoBinding | None:
        matches = [
            repo
            for repo in self.repos
            if repo.provider == provider and repo.full_name == full_name
        ]
        if installation_id is not None:
            exact = [repo for repo in matches if repo.installation_id == installation_id]
            if len(exact) == 1:
                return exact[0]
            if len(exact) > 1:
                return RepoBinding(
                    org_id=exact[0].org_id,
                    repo_id=exact[0].repo_id,
                    provider=provider,
                    full_name=full_name,
                    default_branch=exact[0].default_branch,
                    ambiguous=True,
                )
        unbound = [repo for repo in matches if repo.installation_id is None]
        if len(matches) == 1:
            return matches[0]
        if len(unbound) == 1 and len(matches) == 1:
            return unbound[0]
        if len(matches) > 1:
            return RepoBinding(
                org_id=matches[0].org_id,
                repo_id=matches[0].repo_id,
                provider=provider,
                full_name=full_name,
                default_branch=matches[0].default_branch,
                ambiguous=True,
            )
        return None

    async def settings_for(
        self, *, org_id: uuid.UUID, repo_id: uuid.UUID
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        return (
            self.org_settings.get(org_id),
            self.repo_settings.get((org_id, repo_id)),
        )

    async def put_settings(
        self,
        *,
        org_id: uuid.UUID,
        repo_id: uuid.UUID | None,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        if repo_id is None:
            self.org_settings[org_id] = dict(config)
        else:
            self.repo_settings[(org_id, repo_id)] = dict(config)
        return dict(config)

    async def get_run_by_key(
        self,
        *,
        org_id: uuid.UUID,
        repo_id: uuid.UUID,
        head_sha: str,
        base_sha: str,
        policy_version: str,
    ) -> RunRecord | None:
        for run in self.runs.values():
            if (
                run.org_id == org_id
                and run.repo_id == repo_id
                and run.head_sha == head_sha
                and run.base_sha == base_sha
                and run.policy_version == policy_version
            ):
                return run
        return None

    async def get_run(self, run_id: uuid.UUID) -> RunRecord | None:
        return self.runs.get(run_id)

    async def insert_run(self, record: RunRecord) -> RunRecord:
        existing = await self.get_run_by_key(
            org_id=record.org_id,
            repo_id=record.repo_id,
            head_sha=record.head_sha,
            base_sha=record.base_sha,
            policy_version=record.policy_version,
        )
        if existing is not None:
            return existing
        self.runs[record.id] = record
        self.findings.setdefault(record.id, [])
        return record

    async def update_run(self, run_id: uuid.UUID, **fields: Any) -> RunRecord:
        current = self.runs[run_id]
        updated = current.model_copy(update=fields)
        self.runs[run_id] = updated
        return updated

    async def add_findings(self, run_id: uuid.UUID, findings: list[FindingRecord]) -> None:
        bucket = self.findings.setdefault(run_id, [])
        seen = {item.fingerprint for item in bucket}
        for finding in findings:
            if finding.fingerprint not in seen:
                bucket.append(finding)
                seen.add(finding.fingerprint)

    async def list_findings(self, run_id: uuid.UUID) -> list[FindingRecord]:
        return list(self.findings.get(run_id, []))

    async def supersede_ref(
        self, *, repo_id: uuid.UUID, ref: str | None, except_run_id: uuid.UUID
    ) -> int:
        if not ref:
            return 0
        count = 0
        for run_id, run in list(self.runs.items()):
            if run.repo_id == repo_id and run.ref == ref and run_id != except_run_id:
                if run.status not in {"superseded", "skipped"}:
                    self.runs[run_id] = run.model_copy(
                        update={"status": "superseded", "conclusion": "cancelled"}
                    )
                    count += 1
        return count

    async def published_fingerprints(
        self, *, repo_id: uuid.UUID, pr_number: int | None
    ) -> set[str]:
        if pr_number is None:
            return set()
        found: set[str] = set()
        for pub in self.publications:
            run = self.runs.get(pub["run_id"])
            if run is None or run.repo_id != repo_id or run.pr_number != pr_number:
                continue
            if pub["status"] == "published":
                found.update(pub["fingerprints"])
        return found

    async def add_publication(
        self,
        *,
        org_id: uuid.UUID,
        run_id: uuid.UUID,
        provider: str,
        kind: str,
        status: str,
        external_id: str | None,
        fingerprints: list[str],
        payload: dict[str, Any],
        error: str | None = None,
    ) -> None:
        for pub in self.publications:
            if pub["run_id"] == run_id and pub["provider"] == provider and pub["kind"] == kind:
                pub.update(
                    {
                        "status": status,
                        "external_id": external_id,
                        "fingerprints": fingerprints,
                        "payload": payload,
                        "error": error,
                    }
                )
                return
        self.publications.append(
            {
                "org_id": org_id,
                "run_id": run_id,
                "provider": provider,
                "kind": kind,
                "status": status,
                "external_id": external_id,
                "fingerprints": list(fingerprints),
                "payload": payload,
                "error": error,
            }
        )

    async def list_runs(
        self,
        *,
        org_id: uuid.UUID,
        repo_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[RunRecord]:
        rows = [
            run
            for run in self.runs.values()
            if run.org_id == org_id and (repo_id is None or run.repo_id == repo_id)
        ]
        rows.sort(key=lambda run: run.started_at or _now(), reverse=True)
        return rows[:limit]

    async def remember_installation(self, *, repo_id: uuid.UUID, installation_id: int) -> None:
        for index, repo in enumerate(self.repos):
            if repo.repo_id == repo_id and repo.installation_id is None:
                self.repos[index] = repo.model_copy(update={"installation_id": installation_id})


def _to_record(row: ReviewRun) -> RunRecord:
    return RunRecord(
        id=row.id,
        org_id=row.org_id,
        repo_id=row.repo_id,
        provider=row.provider,
        event_type=row.event_type,
        delivery_id=row.delivery_id,
        ref=row.ref,
        pr_number=row.pr_number,
        base_sha=row.base_sha,
        head_sha=row.head_sha,
        forced=row.forced,
        from_fork=row.from_fork,
        engine=row.engine,
        model_id=row.model_id,
        policy_version=row.policy_version,
        status=row.status,
        conclusion=row.conclusion,
        summary=row.summary,
        error=row.error,
        sender_login=row.sender_login,
        commit_shas=list(row.commit_shas or []),
        metadata=dict(row.metadata_json or {}),
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


class SqlReviewStore:
    """Postgres store. Delivery claims and change-set identity are unique constraints."""

    def __init__(self, sessionmaker: Any) -> None:
        self._sessionmaker = sessionmaker

    async def claim_delivery(self, *, provider: str, delivery_id: str) -> bool:
        async with self._sessionmaker() as session:
            session.add(
                ReviewDelivery(provider=provider, delivery_id=delivery_id, received_at=_now())
            )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return False
        return True

    async def resolve_repo(
        self,
        *,
        provider: str,
        full_name: str,
        installation_id: int | None,
    ) -> RepoBinding | None:
        async with self._sessionmaker() as session:
            stmt = select(Repo).where(Repo.provider == provider, Repo.full_name == full_name)
            rows = list((await session.execute(stmt)).scalars().all())
        if not rows:
            return None
        exact = [
            row
            for row in rows
            if installation_id is not None and row.github_installation_id == installation_id
        ]
        chosen: list[Repo]
        if len(exact) == 1:
            chosen = exact
        elif len(rows) == 1:
            chosen = rows
        else:
            return RepoBinding(
                org_id=rows[0].org_id,
                repo_id=rows[0].id,
                provider=provider,
                full_name=full_name,
                default_branch=rows[0].default_branch,
                ambiguous=True,
            )
        row = chosen[0]
        return RepoBinding(
            org_id=row.org_id,
            repo_id=row.id,
            provider=row.provider,
            full_name=row.full_name,
            default_branch=row.default_branch,
            config_yaml=row.config_yaml,
            installation_id=row.github_installation_id,
        )

    async def settings_for(
        self, *, org_id: uuid.UUID, repo_id: uuid.UUID
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        async with self._sessionmaker() as session:
            stmt = select(ReviewSettingsRow).where(ReviewSettingsRow.org_id == org_id)
            rows = list((await session.execute(stmt)).scalars().all())
        org = next((row.config for row in rows if row.repo_id is None), None)
        repo = next((row.config for row in rows if row.repo_id == repo_id), None)
        return org, repo

    async def put_settings(
        self,
        *,
        org_id: uuid.UUID,
        repo_id: uuid.UUID | None,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        async with self._sessionmaker() as session:
            stmt = select(ReviewSettingsRow).where(ReviewSettingsRow.org_id == org_id)
            rows = list((await session.execute(stmt)).scalars().all())
            current = next((row for row in rows if row.repo_id == repo_id), None)
            if current is None:
                session.add(
                    ReviewSettingsRow(
                        org_id=org_id,
                        repo_id=repo_id,
                        config=config,
                        updated_at=_now(),
                    )
                )
            else:
                current.config = config
                current.updated_at = _now()
            await session.commit()
        return config

    async def get_run_by_key(
        self,
        *,
        org_id: uuid.UUID,
        repo_id: uuid.UUID,
        head_sha: str,
        base_sha: str,
        policy_version: str,
    ) -> RunRecord | None:
        async with self._sessionmaker() as session:
            stmt = select(ReviewRun).where(
                ReviewRun.org_id == org_id,
                ReviewRun.repo_id == repo_id,
                ReviewRun.head_sha == head_sha,
                ReviewRun.base_sha == base_sha,
                ReviewRun.policy_version == policy_version,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
        return _to_record(row) if row is not None else None

    async def get_run(self, run_id: uuid.UUID) -> RunRecord | None:
        async with self._sessionmaker() as session:
            row = await session.get(ReviewRun, run_id)
        return _to_record(row) if row is not None else None

    async def insert_run(self, record: RunRecord) -> RunRecord:
        existing = await self.get_run_by_key(
            org_id=record.org_id,
            repo_id=record.repo_id,
            head_sha=record.head_sha,
            base_sha=record.base_sha,
            policy_version=record.policy_version,
        )
        if existing is not None:
            return existing
        async with self._sessionmaker() as session:
            session.add(
                ReviewRun(
                    id=record.id,
                    org_id=record.org_id,
                    repo_id=record.repo_id,
                    provider=record.provider,
                    event_type=record.event_type,
                    delivery_id=record.delivery_id,
                    ref=record.ref,
                    pr_number=record.pr_number,
                    base_sha=record.base_sha,
                    head_sha=record.head_sha,
                    forced=record.forced,
                    from_fork=record.from_fork,
                    engine=record.engine,
                    model_id=record.model_id,
                    policy_version=record.policy_version,
                    status=record.status,
                    conclusion=record.conclusion,
                    summary=record.summary,
                    error=record.error,
                    sender_login=record.sender_login,
                    commit_shas=record.commit_shas,
                    metadata_json=record.metadata,
                    started_at=record.started_at or _now(),
                    completed_at=record.completed_at,
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raced = await self.get_run_by_key(
                    org_id=record.org_id,
                    repo_id=record.repo_id,
                    head_sha=record.head_sha,
                    base_sha=record.base_sha,
                    policy_version=record.policy_version,
                )
                if raced is None:
                    raise
                return raced
        return record

    async def update_run(self, run_id: uuid.UUID, **fields: Any) -> RunRecord:
        async with self._sessionmaker() as session:
            row = await session.get(ReviewRun, run_id)
            if row is None:
                raise KeyError(run_id)
            if "metadata" in fields:
                row.metadata_json = fields.pop("metadata")
            for key, value in fields.items():
                setattr(row, key, value)
            await session.commit()
            await session.refresh(row)
            return _to_record(row)

    async def add_findings(self, run_id: uuid.UUID, findings: list[FindingRecord]) -> None:
        async with self._sessionmaker() as session:
            run = await session.get(ReviewRun, run_id)
            if run is None:
                raise KeyError(run_id)
            for finding in findings:
                try:
                    async with session.begin_nested():
                        session.add(
                            ReviewFinding(
                                org_id=run.org_id,
                                review_run_id=run_id,
                                fingerprint=finding.fingerprint,
                                category=finding.category,
                                severity=finding.severity,
                                confidence=finding.confidence,
                                file_path=finding.file_path,
                                start_line=finding.start_line,
                                end_line=finding.end_line,
                                side=finding.side,
                                title=finding.title,
                                description=finding.description,
                                evidence=finding.evidence,
                                suggested_fix=finding.suggested_fix,
                                source=finding.source,
                                validation_state=finding.validation_state,
                                resolution_state=finding.resolution_state,
                            )
                        )
                except IntegrityError:
                    continue
            await session.commit()

    async def list_findings(self, run_id: uuid.UUID) -> list[FindingRecord]:
        async with self._sessionmaker() as session:
            stmt = select(ReviewFinding).where(ReviewFinding.review_run_id == run_id)
            rows = list((await session.execute(stmt)).scalars().all())
        return [
            FindingRecord(
                fingerprint=row.fingerprint,
                category=row.category,  # type: ignore[arg-type]
                severity=row.severity,  # type: ignore[arg-type]
                confidence=row.confidence,
                file_path=row.file_path,
                start_line=row.start_line,
                end_line=row.end_line,
                side=row.side,  # type: ignore[arg-type]
                title=row.title,
                description=row.description,
                evidence=row.evidence,
                suggested_fix=row.suggested_fix,
                source=row.source,  # type: ignore[arg-type]
                validation_state=row.validation_state,  # type: ignore[arg-type]
                resolution_state=row.resolution_state,
            )
            for row in rows
        ]

    async def supersede_ref(
        self, *, repo_id: uuid.UUID, ref: str | None, except_run_id: uuid.UUID
    ) -> int:
        if not ref:
            return 0
        async with self._sessionmaker() as session:
            stmt = select(ReviewRun).where(
                ReviewRun.repo_id == repo_id,
                ReviewRun.ref == ref,
                ReviewRun.id != except_run_id,
            )
            rows = list((await session.execute(stmt)).scalars().all())
            count = 0
            for row in rows:
                if row.status not in {"superseded", "skipped"}:
                    row.status = "superseded"
                    row.conclusion = "cancelled"
                    count += 1
            await session.commit()
        return count

    async def published_fingerprints(
        self, *, repo_id: uuid.UUID, pr_number: int | None
    ) -> set[str]:
        if pr_number is None:
            return set()
        async with self._sessionmaker() as session:
            stmt = (
                select(ReviewPublication)
                .join(ReviewRun, ReviewRun.id == ReviewPublication.review_run_id)
                .where(ReviewRun.repo_id == repo_id, ReviewRun.pr_number == pr_number)
            )
            rows = list((await session.execute(stmt)).scalars().all())
        found: set[str] = set()
        for row in rows:
            if row.status == "published":
                found.update(row.fingerprints or [])
        return found

    async def add_publication(
        self,
        *,
        org_id: uuid.UUID,
        run_id: uuid.UUID,
        provider: str,
        kind: str,
        status: str,
        external_id: str | None,
        fingerprints: list[str],
        payload: dict[str, Any],
        error: str | None = None,
    ) -> None:
        async with self._sessionmaker() as session:
            stmt = select(ReviewPublication).where(
                ReviewPublication.review_run_id == run_id,
                ReviewPublication.provider == provider,
                ReviewPublication.kind == kind,
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row is None:
                session.add(
                    ReviewPublication(
                        org_id=org_id,
                        review_run_id=run_id,
                        provider=provider,
                        kind=kind,
                        external_id=external_id,
                        status=status,
                        fingerprints=fingerprints,
                        payload=payload,
                        error=error,
                        published_at=_now(),
                    )
                )
            else:
                row.status = status
                row.external_id = external_id
                row.fingerprints = fingerprints
                row.payload = payload
                row.error = error
                row.published_at = _now()
            await session.commit()

    async def list_runs(
        self,
        *,
        org_id: uuid.UUID,
        repo_id: uuid.UUID | None = None,
        limit: int = 50,
    ) -> list[RunRecord]:
        async with self._sessionmaker() as session:
            stmt = select(ReviewRun).where(ReviewRun.org_id == org_id)
            if repo_id is not None:
                stmt = stmt.where(ReviewRun.repo_id == repo_id)
            stmt = stmt.order_by(ReviewRun.started_at.desc()).limit(limit)
            rows = list((await session.execute(stmt)).scalars().all())
        return [_to_record(row) for row in rows]

    async def remember_installation(self, *, repo_id: uuid.UUID, installation_id: int) -> None:
        async with self._sessionmaker() as session:
            row = await session.get(Repo, repo_id)
            if row is not None and row.github_installation_id is None:
                row.github_installation_id = installation_id
                await session.commit()
