# SelfRepair Roadmap

## Vision
SelfRepair is the unattended, deterministic-first auto-repair engine for
repository fleets. Where rules can fix it, rules fix it. Where they can't, it
escalates to GitPilot under explicit per-repo opt-in. Every change is signed,
scoped, and reversible.

Full design: [`architecture/system-design.md`](architecture/system-design.md).

## Operating decisions (locked)

| Decision | Choice | ADR |
|---|---|---|
| Wedge | Delivery readiness (does this repo install / test / start cleanly?) | — |
| Repair tier | Deterministic-first, AI-second | [0001](adr/0001-deterministic-first.md) |
| Service topology | SelfRepair / GitPilot / OllaBridge as separate services | [0002](adr/0002-three-service-topology.md) |
| State store | Postgres + Arq queue, not JSON files | [0003](adr/0003-postgres-state-store.md) |
| Extensibility | Public Fixer / Scanner SDK, scanners as containers | [0004](adr/0004-plugin-sdk.md) |
| LLM stance | Opt-in per repo via `.selfrepair.yml`, default off | [0001](adr/0001-deterministic-first.md) |

Security-and-compliance is a Phase 2 expansion, not the wedge. CI/CD pipeline
generation is later still.

## 90-day execution plan

### Days 0–30 — backbone
- [ ] Postgres schema (jobs, findings, repairs, audit, provenance) + Alembic.
- [ ] Arq + Redis worker; port `run_daily()` into the state machine.
- [ ] GitHub App auth; webhook ingestion endpoint.
- [ ] OpenTelemetry traces from API → worker → connectors.
- [ ] CI builds the worker container and runs unit tests.

### Days 31–60 — trust
- [ ] OPA-based policy engine consuming `.selfrepair.yml` (resolver landed).
- [ ] PR creation with structured body (template landed) + CODEOWNERS notice.
- [ ] Sigstore signing on every repair commit.
- [ ] Gitleaks gate before push; secret-in-diff aborts the repair.
- [ ] Three reference `Fixer` implementations behind the public SDK.

### Days 61–90 — AI tier
- [ ] Wire `selfrepair.connectors.gitpilot` into `healing_loop` (skeleton landed).
- [ ] OllaBridge as the only LLM seam, with `X-SR-Budget-USD` enforcement.
- [ ] Scanner sidecar runner: Semgrep + Trivy + TruffleHog as the first three.
- [ ] Public dashboard with the four metrics that matter:
  - auto-fix success rate
  - MTTR per finding type
  - $ per repair (model spend)
  - regression rate (PRs reverted within N days)

## Out of scope for the first 90 days
CI/CD pipeline generation, multi-tenant UI, SSO/SAML, on-prem installer, IaC
modules, Slack/Teams bots. All real, all later.

## Status of foundation modules (this branch)

| Module | Status |
|---|---|
| `selfrepair.sdk` (Fixer, Scanner, models, SARIF parser) | landed |
| `selfrepair.state.machine` (job state machine) | landed |
| `selfrepair.config.repo_config` (`.selfrepair.yml`) | landed |
| `selfrepair.connectors.gitpilot` (HTTP + SSE) | landed |
| Postgres schema + Alembic migrations | TODO |
| Arq worker | TODO |
| OPA policy bundle | TODO |
| Reference fixers | TODO |
| Scanner sidecar runner | TODO |
| Sigstore signing + Gitleaks gate | TODO |
