---
title: SelfRepair
emoji: "\U0001F6E0️"
colorFrom: green
colorTo: gray
sdk: docker
pinned: false
license: apache-2.0
app_port: 7860
short_description: Repository maintenance console (dry-run safe)
---

# SelfRepair — repository maintenance console

SelfRepair is a generic repository maintenance product. It **diagnoses** a
repository, builds a **repair plan**, delegates code changes to **GitPilot**,
validates them in **MatrixLab**, and **reports** — using models served through
**OllaBridge Cloud**. SelfRepair never writes code itself.

This Space is the admin console: log in, then open **Connections** to wire the
generic products together and verify the pipeline end-to-end.

## Connections

| Provider | What it is | Default |
|----------|------------|---------|
| OllaBridge Cloud | Inference gateway (OpenAI-compatible) | `https://ruslanmv-ollabridge.hf.space/v1` |
| GitPilot | AI coder (writes patches, dry-run) | `https://ruslanmv-gitpilot.hf.space` |
| MatrixLab | Sandbox validation provider | `https://ruslanmv-matrixlab.hf.space` |

Each connection has a live **Test** button. OllaBridge takes an `ob_test_…` /
`ob_live_…` key; GitPilot and MatrixLab take an optional token. Secrets are
encrypted at rest (Fernet) and masked in the UI.

## Code reviews and routines

The console includes the **Reviews** and **Routines** pages. Running them needs
the full SelfRepair server: API, Arq worker, PostgreSQL, Redis, and a GitHub App
for webhooks and the `SelfRepair / Review` check. This Space has none of those,
so those pages show empty lists and the opt-in defaults (`enabled: false`,
`engine: deterministic`). Saving review settings or creating a routine answers
`501` with that explanation. The Space never shows a review it did not run.

## Updating this Space

The Space serves a prebuilt copy of `frontend/` from `webapp/spa`. Before
pushing this folder to the Space, rebuild it from the repository root:

```bash
make hf-space
```

Then push `deploy/huggingface/` as the Space repository root.

### Automatic deploys

`.github/workflows/deploy-hf-space.yml` does all of this on every push to
`master` that touches `deploy/huggingface/`, `frontend/` or the build script,
and on demand from the Actions tab (**Deploy Hugging Face Space → Run workflow**).
It rebuilds the console, tests the Space API, builds the image and checks
`/health`, pushes the tracked files of this folder to
[`ruslanmv/selfrepair`](https://huggingface.co/spaces/ruslanmv/selfrepair), and
waits until the Space runs that exact commit and answers `/health`.

It needs one repository secret, `HF_TOKEN`: a Hugging Face token with write
access to the Space. `HF_USERNAME` and `SPACE_NAME` repository variables
override the target (default `ruslanmv` / `selfrepair`). Space secrets such as
`ADMIN_PASSWORD` or `DATABASE_URL` stay in the Space settings on Hugging Face.

## Golden rules

- **Only OllaBridge holds `HF_TOKEN`.** This Space never stores it — it talks
  to models exclusively through OllaBridge using an `ob_*` key.
- Public demo is **dry-run only**: no real PRs are created.

## Default credentials

- Username: `admin`
- Password: `selfrepair2024` (override with the `ADMIN_PASSWORD` Space secret)

> Change the admin password after first login via **Settings**.

## Accounts & email verification

Sign up creates an account in **Postgres** with an unverified email, sends a
verification link via **Mailtrap**, and blocks sign-in until the email is
confirmed. Password reset works the same way. One-time tokens and rate limits
live in **Upstash Redis**. If Postgres is unreachable the app falls back to
ephemeral SQLite so the Space still runs.

## Environment / Space secrets

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Postgres DSN (e.g. Neon `postgresql://…?sslmode=require`). Falls back to SQLite if unset/unreachable. |
| `UPSTASH_REDIS_REST_URL` | Upstash Redis REST URL (verification/reset tokens + rate limits) |
| `UPSTASH_REDIS_REST_TOKEN` | Upstash Redis REST token |
| `MAILTRAP_TOKEN` | Mailtrap API token for transactional email |
| `MAILTRAP_SENDER` | Sender address (default `hello@demomailtrap.co`) |
| `APP_BASE_URL` | Public base URL used in email links (default `https://ruslanmv-selfrepair.hf.space`) |
| `SELFREPAIR_SECRET_KEY` | Fernet key for encrypting stored connection secrets |
| `ADMIN_PASSWORD` / `ADMIN_EMAIL` | Seed admin account (pre-verified) |
| `SESSION_SECRET` | Session-cookie signing secret (optional) |
| `SELFREPAIR_DEMO_LINKS` | `1` to also show verification/reset links in the UI (demo only) |

`GET /health` reports which backends are active (`db`, `redis`, `email`).

See [GitHub](https://github.com/ruslanmv/SelfRepair) for full documentation.
