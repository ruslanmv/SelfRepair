# ADR-0003: Postgres + Arq queue replace JSON-on-disk state

## Status
Accepted — 2026-05-01

## Context
SelfRepair currently persists run state as JSON files under `state/`. This
breaks down the moment we need:

- concurrent runs across the fleet,
- multi-tenant isolation,
- "have we already opened a PR for this finding on this commit SHA?" lookups,
- audit retention and partitioning,
- horizontal scaling of workers.

## Decision
- **Postgres** for all durable state: jobs, findings, repairs, audit, provenance.
- **Redis + Arq** for the job queue.
- **Findings deduplicate** by stable fingerprint (see `selfrepair.sdk.models.Finding`).
- **Audit log** is append-only and partitioned by month.
- **`org_id`** is on every table from day one, even in single-tenant installs.

## Consequences
- Hard dependency on Postgres + Redis — both commodity, both fine.
- The git tree remains the source of truth for repairs; if the DB burns, the
  repair branches and PRs are recoverable.
- One-way migration of legacy `state/*.json` content; old format is deprecated.

## Rejected alternatives
- **SQLite.** Fine for single-node demos; falls over at fleet scale and has poor
  concurrent-write semantics.
- **Just a key-value store.** No relational queries, no audit partitioning,
  no schema evolution story.
