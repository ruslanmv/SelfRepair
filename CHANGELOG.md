# Changelog

## Unreleased

### Added

- **HF Space console (`ruslanmv/selfrepair`)**: one unified React UI; email-verified auth (Neon Postgres + Upstash Redis + Mailtrap), admin panel with a protected **root** superuser, control-plane intake (`POST /v1/plans`) + Inbox/notifications, and a worker that attaches a **GitPilot dry-run patch preview** to each maintenance report.
- **End-to-end real backend behind the SPA**. Every operator-console
  surface now reads from the real `selfrepair.api` `/v1` endpoints; the
  previous `SR_DATA` mock stays in-tree only for offline dev mode.
- **API surface**: `auth`, `me`, `orgs`, `repos`, `findings`,
  `repairs`, `jobs`, `dashboard`, `audit`, `policies`, `schedules`,
  `integrations` (and the existing `issues`, `ci`, `webhooks`,
  `metrics`). Every list is cursor-paged and `org_id`-scoped through
  the new `CtxDep`.
- **SSE live job stream** (`GET /v1/jobs/{id}/events/stream`) backed by
  a Redis pub/sub publish in the worker pipeline. Replaces the
  client-side `setTimeout` fake stream in `JobDetail.jsx`.
- **Cookie sessions**: `selfrepair.auth.{passwords,sessions,cookies,middleware}`,
  `/v1/auth/{login,logout,refresh}`, `/v1/me`, `/v1/orgs/current`.
  Stored format is self-describing PBKDF2-HMAC-SHA256 so iteration
  parameters are easy to rotate.
- **9 new operational tables** in `0004_console_ops` plus
  `user_credential` in `0005_auth`. Indexes for the dashboard and
  list endpoints (`ix_job_console_list`, `ix_repair_created_desc`,
  `ix_audit_log_org_id_desc`, `ix_finding_console_list`).
- **TanStack Query foundation** in `frontend/src/api` and
  `frontend/src/hooks`. Native fetch wrapper, opaque cursor encoder,
  `ApiError` with `.status`/`.detail`, `EventSource` helper for SSE.

### Changed

- `docker-compose.yml` boots the real product surface: postgres,
  redis, alembic-upgrade-on-boot, `selfrepair.api`, `arq` worker,
  nginx-served SPA. Healthchecks on every service.
- Default `Dockerfile` `CMD` now boots `selfrepair.api.main:app`.
  Same image is reused by the worker (`arq`) and the migrate
  one-shot (`alembic upgrade head`).
- Sidebar logout calls `/v1/auth/logout` and routes to the new
  `Login.jsx` surface; previously it only refreshed the page.
- `routes/jobs.py` is now a full CRUD surface: list / create / detail
  / events (paginated + SSE) / cancel / retry, all org-scoped.
- `routes/issues.py` GET endpoint resolves org via `CtxDep` instead of
  a mandatory `org_id` query parameter.

### Removed

- `<StubPage>` for `policies` / `audit` / `settings` routes. Real
  surfaces ship instead.
- `setTimeout`-driven event simulation in `JobDetail.jsx`.
- `SR_DATA` imports from every surface except the kept-for-MSW
  `frontend/src/data/mock.js` (and a single reuse of the `spark()`
  helper for decorative sparklines on `Overview.jsx`).
