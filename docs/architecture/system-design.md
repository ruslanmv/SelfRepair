# AI Secure Delivery Copilot — System Design

This is the executable design that sits underneath `docs/ROADMAP.md`. Every
decision here either has an ADR or is downstream of one.

## 1. Design principles

1. **SelfRepair owns the repo, GitPilot owns the brain, OllaBridge owns the model.**
   Three services, one responsibility each. No service ever talks to a model
   directly except OllaBridge.
2. **Deterministic-first, AI-second.** A finding is fixed by a `Fixer` (rule)
   when possible, escalated to GitPilot only when no rule matches *and* the
   repo opted in.
3. **The git tree is the source of truth.** Job state is in Postgres, but the
   repair itself is a branch + PR. If the DB burns, you reconstruct from git.
4. **Every repair is signed, scoped, and reversible.** Sigstore-signed commit,
   single-purpose branch, opens a PR — never pushes to default.
5. **Sandbox is hermetic and disposable.** No persistent volume, no secrets,
   no outbound network except an allowlisted package mirror.
6. **Tenancy is a row, not a deployment.** `org_id` on every table from day one.
7. **The plugin SDK is the product.** Core ships reference plugins; the long
   tail is community-built.

## 2. System topology

```
                  ┌──────────────────────────────────────────────┐
                  │  Clients: web UI, VS Code, CLI,              │
                  │           GitHub/GitLab webhooks             │
                  └──────────────────────────────────────────────┘
                                       │ HTTPS
                                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│  selfrepair-api  (FastAPI, stateless, horizontally scaled)            │
│  • REST + /v1/rpc (A2A) + /webhooks/{provider}                        │
│  • Auth: GitHub App / GitLab App / OIDC for humans                    │
│  • Validates, enqueues jobs, serves dashboards                        │
└──────────────────────────────────────────────────────────────────────┘
        │ enqueue                              │ read
        ▼                                      ▼
┌─────────────────────┐             ┌─────────────────────┐
│  Redis + Arq queue  │             │  Postgres (state,   │
│  (jobs, rate-limit) │             │  findings, audit)   │
└─────────────────────┘             └─────────────────────┘
        │ pull
        ▼
┌──────────────────────────────────────────────────────────────────────┐
│  selfrepair-worker  (N replicas; one job = one repo run)              │
│  Stages: clone → analyze → scan → plan → repair → validate → publish  │
│         each stage emits events on NATS / Redis Pub/Sub               │
└──────────────────────────────────────────────────────────────────────┘
        │                              │                        │
        │ scanner gRPC                 │ HTTP repair             │ exec in
        ▼                              ▼                        ▼
┌────────────────────┐      ┌────────────────────┐    ┌────────────────────┐
│ scanner sidecars   │      │  gitpilot-agent    │    │ matrixlab-sandbox  │
│ semgrep, trivy,    │      │ (Explorer→Planner  │    │ (firecracker /     │
│ trufflehog, syft,  │      │  →Coder→Reviewer)  │    │  gVisor pod, no    │
│ licensee, opa-eval │      │                    │    │  egress except     │
│                    │      │  └─► OllaBridge ───┼────┤  pip/npm mirror)   │
└────────────────────┘      └────────────────────┘    └────────────────────┘
```

## 3. Job state machine

A repair run is a sequence of explicit transitions. Every transition is an
audit row. Retries are idempotent on `(job_id, stage, repo_sha)`.

See `selfrepair/state/machine.py` for the canonical transition table.

```
queued → cloning → analyzing → scanning → planning
                                              │
                                              ├── (no findings) → completed
                                              ▼
                                          repairing → validating
                                                          │
                                                          ├── failed_validation → escalated
                                                          ▼
                                                      publishing → awaiting_review
                                                                      │
                                                                      ├── merged
                                                                      ├── closed
                                                                      └── stale (TTL)
```

Any active state may transition to `escalated` on unhandled error, carrying a
full diagnostic bundle (logs, sandbox stdout, model traces).

## 4. Data model

```sql
org(id, name, plan, created_at)
user(id, org_id, email, role)               -- admin | reviewer | viewer

repo(id, org_id, provider, full_name, default_branch, last_seen_sha,
     config_yaml, archived_at)
repo_credential(repo_id, kind, secret_ref)  -- secret_ref → KMS, never plaintext

job(id, org_id, repo_id, trigger, state, started_at, finished_at,
    sandbox_id, error_kind)
job_event(id, job_id, ts, stage, level, message, payload_jsonb)

finding(id, org_id, repo_id, fingerprint, kind, severity, cwe, cve,
        first_seen_sha, last_seen_sha, first_seen_at, status,
        suppressed_until, suppressed_reason)
        -- fingerprint = hash(rule_id, file_path, normalized_snippet)
        -- status: open | fixed | wont_fix | suppressed

repair(id, finding_id, job_id, fixer_id, mode, model_id, prompt_hash,
       diff_sha, sandbox_result, signed_commit_sha, pr_url, state)
       -- mode: deterministic | llm
       -- state: planned | applied | validated | published | merged | reverted

policy_decision(id, repair_id, rule_id, outcome,
                requires_approval, approver_id, decided_at)

provenance(id, repair_id, builder, materials_jsonb, attestation_blob)

audit_log(id, org_id, actor, action, target_type, target_id, ts, ip, payload)
```

Three details that matter:

- **Findings have stable fingerprints.** Same vuln seen 47 times = one row.
- **Repairs are separate from findings.** Multiple attempts per finding, each
  with its own model trace.
- **Provenance is its own table.** SLSA attestations attach to repairs and
  survive even if the repair branch is deleted.

## 5. Service contracts

### 5.1 SelfRepair → GitPilot

```http
POST /v1/agents/repair                       (on the GitPilot service)
Authorization: Bearer <service token; mTLS in prod>
Idempotency-Key: <repair_id>

{
  "repair_id": "rep_01H...",
  "permission_mode": "plan",                 // plan | ask | auto
  "workspace": {
    "kind": "git_bundle",                    // bundle, not creds — sandbox is hermetic
    "url": "s3://sr-sandbox/abc.bundle",
    "checkout": "main"
  },
  "context": { "finding": {...}, "previous_attempts": [...], "repo_config": {...} },
  "tools_allowed": ["read_file", "edit_file", "run_tests"],
  "tools_denied":  ["network", "git_push"],
  "budget": { "tokens": 200000, "wall_seconds": 600, "usd": 0.50 },
  "model_routing": { "prefer": ["qwen2.5:32b", "claude-haiku-4-5"] }
}

→ 202 Accepted, then SSE stream:
event: plan         data: { steps: [...] }
event: tool_call    data: { tool, args }
event: tool_result  data: { ... }
event: edit         data: { path, diff }
event: done         data: { patch_url, signed_provenance }
```

Hard rules baked into the contract:
- GitPilot **never** sees a real git remote token — it gets a bundle, returns a patch.
- `tools_denied` is enforced server-side by GitPilot's permissions module.
- `Idempotency-Key = repair_id` so SelfRepair can retry on timeout safely.
- Budget is a contract; GitPilot must abort and report partial when exceeded.

Reference implementation: `selfrepair/connectors/gitpilot.py`.

### 5.2 SelfRepair / GitPilot → OllaBridge

OllaBridge stays an OpenAI-compatible `/v1/chat/completions` endpoint with two
add-ons:

- `X-SR-Tenant`, `X-SR-Job`, `X-SR-Repair` headers → end-to-end trace correlation.
- `X-SR-Budget-USD` → server-side cost enforcement; returns 429 when exceeded.

Both services share a `model_catalog.yaml` so "default code-fix model" means
the same thing in both places.

### 5.3 Scanner plugin contract

```yaml
# /plugin.yaml inside the scanner image
kind: scanner
id: semgrep
version: 1.84.0
inputs:  [workspace_path]
outputs: [findings.sarif]
runtime:
  image: returntocorp/semgrep:1.84
  cmd: ["semgrep", "--config=auto", "--sarif", "-o", "/out/findings.sarif", "/in"]
  network: none
  cpu: "1"; memory: "2Gi"; timeout: 300s
```

The worker mounts the repo read-only at `/in`, an empty `/out`, runs the
container, and parses the SARIF. **Adding a scanner = shipping an image.** No
Python change required.

### 5.4 Fixer plugin contract

See `selfrepair/sdk/fixer.py`. Three reference fixers ship in core; everything
else is a plugin discovered via entry points.

## 6. The `.selfrepair.yml` config

The contract between platform team and the tool. Without the file, defaults
are conservative: dry-run, no LLM, no auto-merge.

See `examples/.selfrepair.yml` and `selfrepair/config/repo_config.py`.

## 7. Security model

Six things, in the order they kill enterprise deals:

1. **No long-lived credentials.** GitHub App installation tokens (1h TTL),
   short-lived OIDC tokens for cloud secrets. PATs are debug fallback only.
2. **Sandbox is hermetic.** gVisor pod, no host network, egress through a
   transparent proxy that allowlists `pypi.org`, `registry.npmjs.org`, etc.
3. **Signed commits.** Sigstore keyless signing via GitHub OIDC.
4. **Provenance attestations.** SLSA v1.0 build provenance per repair.
5. **Secret-scan the diff before push.** Gitleaks runs as the last gate.
6. **All AI prompts and outputs logged** (with PII redaction), retention
   configurable per tenant.

## 8. Deployment

Development: docker-compose with one Postgres, one Redis, one OllaBridge stub.
Production: a single Helm chart that deploys api / worker / web with a
Postgresql operator and a Redis sentinel. GitPilot and OllaBridge each have
their own charts and are pulled in as dependencies.
