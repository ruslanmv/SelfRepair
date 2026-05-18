# SelfRepair — Plan to Remove Frontend Placeholders and Ship a Real Backend-Driven Console

Branch: `claude/review-selfrepair-placeholders-MtJrP`
Scope: turn the `frontend/` demo console into a real product driven by a single
consolidated `selfrepair/api` backend.

This document started as the audit-driven plan; it is now the
implementation log. The status table at the top reflects what landed
on this branch (read top-down). Architectural reasoning is preserved
below for future contributors.

## Status

| Milestone | State | Notes |
|---|---|---|
| **M0** Consolidate compose | ✅ shipped | docker-compose runs `selfrepair.api.main:app` + arq worker + postgres + redis + frontend behind nginx with health checks. The legacy `backend.app` engine package stays in-tree as an internal helper. |
| **M1** Read APIs | ✅ shipped | `repos`, `findings`, `repairs`, `jobs` (list + detail), `dashboard`, `audit`. All cursor-paged, all `org_id`-scoped through `CtxDep`. |
| **M2** Mutating APIs | ✅ shipped | `POST /v1/jobs`, `findings/{suppress, mark-fixed, run-repair}`, `repairs/{approve, reject, rerun-validation, publish-pr}`, `repos/sync`. Every mutation writes an `audit_log` row; provider-touching actions enqueue the worker. |
| **M3** Live job stream | ✅ shipped | `GET /v1/jobs/{id}/events/stream` (SSE) plus a Redis pub/sub hook in the worker pipeline. The SPA's JobDetail uses `useJobEventStream`; the previous `setTimeout` fake stream is gone. |
| **M4** Auth/session | ✅ shipped | Cookie session backed by `session` + `user_credential` tables, PBKDF2 hashing, `SessionMiddleware`, `/v1/auth/{login,logout,refresh}` + `/v1/me` + `/v1/orgs/current`. Sidebar logout calls the real endpoint. |
| **M5** Stub pages | ✅ shipped | `Login`, `Policies`, `AuditLog`, `Settings` surfaces are real and bound to `/v1/{policies,audit,integrations,me}`. App.jsx no longer renders `<StubPage>` for the four core routes (about/help remain as harmless placeholders). |
| **M6** Production hardening | 🟡 partial | real `/readyz`, CORS allowlist, structured cursor, audit on every mutation, app-state Arq pool. Still TODO: rate limit middleware, Idempotency-Key enforcement, OpenTelemetry, real artifact storage for diff/SBOM/provenance bundles. |
| **M7** Enterprise auth | not started | OIDC, SAML, SCIM, RBAC roles. |

## Frontend mock retirement

`grep -r SR_DATA frontend/src` after batch 21 finds **only** the
exports inside `frontend/src/data/mock.js` itself (the named `spark`
helper is reused by `Overview.jsx` for decorative sparklines, and the
module is kept for MSW dev mode behind `VITE_USE_MOCKS`). Every
surface reads from the real API:

* `Overview` → `useDashboard()`
* `Repos` / `RepoDetail` → `useRepos`, `useRepoSummary`, `useFindings`, `useJobs`, `useSyncRepos`
* `Findings` → `useFindings` (+ `useSuppressFinding` / `useMarkFindingFixed` / `useRunRepairForFinding` ready for the triage drawer)
* `Repairs` / `RepairDetail` → `useRepairs`, `useRepair`, `useRepairDiff`, `useApproveRepair` / `useRejectRepair` / `useRerunValidation` / `usePublishPr`
* `Jobs` / `JobDetail` → `useJobs`, `useJob`, `useJobEvents`, `useJobEventStream`, `useCreateJob`, `useCancelJob`, `useRetryJob`
* `OpenIssues` → `useIssues` + `useSyncIssues` + `useRunRepairFromIssue`
* `Policies` → `usePolicies` + `usePolicyDecisions`
* `AuditLog` → `useAudit` + the streaming `/v1/audit/export` endpoint
* `Settings` → `useSession` + `useIntegrations` + `useConnectIntegration`

## Architecture (final)

```text
React SPA (frontend/) — React 18 + TanStack Query 5 + native fetch
        │ /api/v1/* JSON, /api/v1/jobs/{id}/events/stream SSE
        ▼
selfrepair/api (FastAPI, the only public API)
   ├─ SessionMiddleware → request.state.session_user_id / org_id
   ├─ CORSMiddleware → allowlisted origins (no wildcard in prod)
   ├─ REST: auth, me, orgs, repos, findings, repairs, jobs, dashboard,
   │        audit, policies, schedules, integrations, issues, ci
   └─ SSE: /v1/jobs/{id}/events/stream
        │ enqueue(arq) for repair / sync / publish-pr / rerun-validation
        ▼
selfrepair/worker (arq) — pipeline: clone → scan → analyze → plan →
        repair (matrixlab sandbox) → validate → policy → sign/provenance
        → publish (gitpilot). After every state transition the pipeline
        publishes the new job_event row to Redis pub/sub for SSE.
        │
        ▼
Postgres (source of truth) + Redis (queue + SSE bus + sessions cache)
Object storage (logs, patches, SBOMs, attestations — wired to
  Artifact rows; serving endpoint lands in M6).
```

## Schema (final)

Started from the existing 0001..0003 migrations and added
`0004_console_ops.py` and `0005_auth.py` on this branch:

* **0004_console_ops** — `integration_connection`, `api_token`,
  `session`, `user_invitation`, `repair_schedule`, `repo_scan_snapshot`,
  `artifact`, `notification`, `policy_bundle_version`. Plus indexes
  the §1.4 plan called out: `ix_job_console_list`,
  `ix_repair_created_desc`, `ix_audit_log_org_id_desc`,
  `ix_finding_console_list` (all `CREATE INDEX IF NOT EXISTS` so reruns
  / hot-patched deployments don't fail).
* **0005_auth** — `user_credential` (PK = user_id; password_hash in a
  self-describing `pbkdf2_sha256$<iters>$<salt>$<digest>` format).

## Commands

```bash
cp .env.example .env
docker compose up
# api  on :8000
# spa  on :8080
# worker, postgres, redis on the compose network
```

First-time bootstrap creates an empty database; insert an `org` +
`user_account` + `user_credential` row to authenticate. (A bootstrap
script is the obvious next addition; the plan keeps it out of M0–M5.)

## What is intentionally still demo-flavoured

* `frontend/src/data/mock.js` ships in the bundle so MSW dev mode (off
  by default) and Storybook can keep working.
* `Overview.jsx` uses `spark()` to draw decorative sparklines; the
  values themselves come from `/v1/dashboard`, the lines are visual
  noise until the `repo_scan_snapshot` read endpoint lands.
* `RepairDetail.jsx`'s diff tab shows the `diff_sha` and a note that
  the artifact endpoint lands in M6; we do not fabricate a fake patch.
* `Run repair` / `Audit log drawer` / `Auto-repair modal` /
  `ChatDock` features are still UI-only — the matching backend
  endpoints exist (`/v1/jobs`, `/v1/audit/scopes/...`,
  `/v1/schedules`); rewiring those modals is the obvious M5/M6
  follow-up.

## Recommendation

The fastest path from 1.0 to a fully-hardened product is M6: real
artifact storage (so `RepairDetail`'s diff / sandbox / provenance tabs
render real bytes), Idempotency-Key middleware on every mutation, a
rate-limit middleware in front of `/v1/auth/login`, and an
OpenTelemetry pipeline so the API/worker share a trace per job.
