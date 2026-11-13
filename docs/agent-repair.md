# Agent repair: fixes for AI-agent issues sent by LangReplay

LangReplay replays an AI agent's failed production conversations and turns one into a **fix case** with approved
acceptance criteria. When a developer clicks **Propose a fix** on that case, LangReplay sends SelfRepair a
sanitized evidence package and the repository pinned to one commit. SelfRepair asks GitPilot for a read-only plan,
waits for a person to approve it, has GitPilot make the patch inside the approved files, checks the patch on the
pinned commit, and later pushes a candidate branch and opens a **draft** pull request.

An AI-agent issue is not a repository-health finding, so it does not go through the scan pipeline. It has its own
small path, `/v1/agent-repairs`, built on SelfRepair's database, audit log, worker queue and GitPilot client.

| Who | Owns |
|---|---|
| LangReplay | The evidence, the repair-attempt record, the replay that verifies the patch, the verdict. |
| SelfRepair | Intake, service authentication, the repository allow-list, approval and scope enforcement, the workspace, static checks, job history, audit, the candidate branch, the draft PR. |
| GitPilot | The plan (read-only planner) and the patch (`/repair` in `dry_run`). |
| GitHub | The draft pull request and the human code review. |

Nothing on this path merges, deploys, or writes outside the approved files.

## 1. Turn it on

The intake is off until four settings are present. Without them every request gets `503`.

| Variable | Meaning |
|---|---|
| `SELFREPAIR_AGENT_REPAIR_TOKEN` | Bearer token LangReplay presents. **Required.** |
| `SELFREPAIR_AGENT_REPAIR_SECRET` | Shared secret for the HMAC signature. **Required.** |
| `SELFREPAIR_AGENT_REPAIR_ORG_ID` | The org every agent repair belongs to. It never comes from a header. **Required.** |
| `SELFREPAIR_AGENT_REPAIR_REPOS` | Comma-separated repository URLs that may be repaired (compared without case, `.git` or a trailing `/`). **Required.** |
| `SELFREPAIR_AGENT_REPAIR_CHECKS` | JSON list of argv lists run on base commit + patch, e.g. `[["python","-m","pytest","-q"]]`. No shell. Without one, no draft PR can be opened. |
| `SELFREPAIR_AGENT_REPAIR_CHECK_TIMEOUT` | Seconds per check command. Default `600`. |
| `SELFREPAIR_AGENT_REPAIR_MAX_RETRIES` | Implementations allowed after the first one. Default `2`. |
| `SELFREPAIR_AGENT_REPAIR_GITHUB_TOKEN` | Token that may push `langreplay/*` branches and open pull requests. Give it no merge rights. |
| `SELFREPAIR_AGENT_REPAIR_CODER_PROVIDER`, `_CODER_MODEL` | Passed to GitPilot. Default `ollabridge` / `code-coder`. |
| `SELFREPAIR_AGENT_REPAIR_ALLOW_DEMO_CODER` | `true` only for a trial: accept GitPilot's demo coder. |
| `SELFREPAIR_AGENT_REPAIR_INLINE` | `true` only in a single-process setup without Redis: run the steps in the API process. |

GitPilot is found the way the rest of SelfRepair finds it (`resolve_service("gitpilot")`: the org's saved service
connection, else `SELFREPAIR_GITPILOT_URL` or `GITPILOT_URL`). Run GitPilot with `GITPILOT_CODER_DEMO=false` and `GITPILOT_API_TOKEN`
set. Workspaces go under `$SELFREPAIR_SANDBOX_WORKDIR/agent-repair`.

Apply the migration (`alembic upgrade head`, revision `0009_agent_repair`) and restart the API and the worker. The
worker runs the steps as the `agent_repair_step` job.

On the LangReplay side, point `repair.service` in `langreplay.yaml` at SelfRepair with the same token and secret
(LangReplay's `docs/repair.md`).

## 2. Authentication

Every request carries:

| Header | Value |
|---|---|
| `Authorization` | `Bearer <SELFREPAIR_AGENT_REPAIR_TOKEN>`, compared in constant time |
| `X-LangReplay-Timestamp` | Unix seconds; more than 300 s off is refused |
| `X-LangReplay-Signature` | `v1=` + hex HMAC-SHA256 of `timestamp + "." + body` with `SELFREPAIR_AGENT_REPAIR_SECRET` |

A bad token, an old timestamp or a wrong signature gets `401`. The body is parsed from the exact bytes that were
signed. GET requests sign an empty body. Jobs of another org answer `404`.

## 3. States

```text
planning ─▶ plan_ready ─▶ implementing ─▶ patch_ready ─▶ pr_draft
   │                          │      ▲          │
   └─▶ failed ◀───────────────┘      └──────────┘  an approved retry (from patch_ready or failed)
 any state except pr_draft and failed ─▶ cancelled
```

The state only moves along these arrows; any other move is refused (`409`), including a second cancel.

## 4. Endpoints

| Method and path | Body | Answer |
|---|---|---|
| `POST /v1/agent-repairs` | `source:"langreplay", attempt_id, case_id, evidence_id, evidence, repository{url, base_commit, ref}, mode:"plan", requested_by` | `202 {job_id, state:"planning", evidence_id, gitpilot_run_id}` |
| `GET /v1/agent-repairs/{job}` | | `{job_id, state, attempt_id, case_id, evidence_id, repository, coder, gitpilot_run_id, plan, scope, patch, patch_sha256, changed_files, branch, static_checks, pr, retries, error, updated_at}` |
| `GET /v1/agent-repairs/{job}/events?after=n` | | `{items:[{seq, at, stage, level, message}], next}` |
| `POST /v1/agent-repairs/{job}/approve` | `approved_by, approved_at, what:"plan"\|"retry", scope[], plan_sha256, retry` | `{job_id, state:"implementing"}` |
| `POST /v1/agent-repairs/{job}/draft-pr` | `title, body, draft:true, requested_by, patch_sha256, verification_run` | `{url, number, draft:true}` |
| `POST /v1/agent-repairs/{job}/cancel` | `reason` | `{job_id, state:"cancelled"}` |

`patch` is only shown when the state is `patch_ready` or `pr_draft`. `plan` is `{summary, files, risks,
verification, steps}`. `coder` is `{agent, version, provider, model, demo}`. `static_checks` is `{status: passed |
failed | not_configured, detail, commands[{argv, exit, seconds, tail}]}`.

**Intake** refuses a repository that is not on the allow-list (`403`), an evidence package whose canonical JSON
does not hash to `evidence_id` or that names another case (`400`), and a `base_commit` that is not a full 40-character
commit id (`422`). It is idempotent per `attempt_id`: the same attempt with the same evidence returns the first job and
queues nothing; with other evidence it gets `409`. Other repeated actions start nothing: the state machine refuses
them with `409`.

## 5. What it enforces

1. **The pinned commit.** The workspace is a new folder, fetched and checked out at `base_commit` (detached), and
   `HEAD` is verified to equal it. No fallback to a branch or another commit. A patch that does not apply to that
   commit fails the job.
2. **A read-only plan.** Planning uses GitPilot's planner (`POST /api/chat/plan`), not `/repair`. Only the files it
   would create, modify or delete count. A step that would run a command becomes a risk, not a file. A plan with no
   file fails.
3. **No code change without a person.** `/repair` is only called after `approve`. The approved scope may only narrow
   the plan's files (`422` otherwise). A retry needs a new approval, `retry` must be the next number, and the count
   is bounded by `SELFREPAIR_AGENT_REPAIR_MAX_RETRIES`.
4. **The scope, twice.** GitPilot gets `allowed_paths` = the approved scope and `forbidden_paths` = SelfRepair's
   forbidden list (the one reviewer remediation uses: `.env`, `secrets/**`, anything named like a token or a secret,
   `migrations/**`, `infra/prod/**`), plus `human_approval: true` and `auto_merge: false` (GitPilot ignores that
   field today; `dry_run` never pushes anything, so nothing can be merged from it). Every path in the returned
   patch and in `changed_files` is checked again: inside the scope, not absolute, no `..`, not forbidden.
5. **No demo output.** `GET /repair/health` is read before each GitPilot call. `coder_demo: true` fails the job
   unless `SELFREPAIR_AGENT_REPAIR_ALLOW_DEMO_CODER` is set, and `coder.demo` reports it. SelfRepair's GitPilot client
   turns a connection error into a stub: that is a failure here, never a patch. A status other than `ok`, or an empty
   patch, is a failure too.
6. **Untrusted evidence.** The evidence reaches GitPilot inside `<untrusted-evidence>` tags with an instruction to
   treat it as data. LangReplay has already removed secret-like arguments and masked customer text.
7. **Checks without credentials.** The configured commands run as argv lists, without a shell, with a timeout each,
   and with every environment variable that looks like a token, secret, password or key removed. The workspace is
   deleted afterwards, also on failure.
8. **Draft only.** `draft-pr` needs `patch_ready`, static checks that passed, the `patch_sha256` of the patch
   SelfRepair produced (so LangReplay verified this patch and no other), and LangReplay's `verification_run`. It
   clones the pinned commit again, applies the patch, commits it on `langreplay/<attempt id>` (no other branch name
   is pushed), pushes that one ref without `--force`, and opens the pull request with `draft=True`, checking that
   GitHub reports it as a draft. The token goes through git's environment configuration, never on a command line.
9. **Explicit failures.** Every failure is written to the job (`error`) and its events with the reason. An
   unexpected exception ends the step as `failed` ("internal error while …"), never as a job stuck in `planning`. When
   the worker queue is unavailable the job fails with that reason, unless `SELFREPAIR_AGENT_REPAIR_INLINE` is set.
10. **Audit.** Audit rows (`target_type: agent_repair`) for `agent_repair.create`, `agent_repair.approve`,
    `agent_repair.gitpilot_plan` and `agent_repair.gitpilot_repair` (before each GitPilot call),
    `agent_repair.draft_pr` and `agent_repair.cancel`. An operator action's audit row is written in the same
    transaction as its state change.

## 6. Limits

- **Cancellation is cooperative.** Cancel moves the job to `cancelled` at once. A GitPilot call already running is
  not interrupted: it finishes, its result is discarded (a `discarded` event says so), and its workspace is deleted.
- **GitPilot cannot pin a commit.** `/repair` clones the branch (`ref`) itself, so the patch is made against that
  branch's head. SelfRepair enforces the pin by applying the patch to `base_commit`; if the branch moved and the
  patch no longer applies, the job fails rather than using the newer code.
- **GitHub only** for the draft pull request (PyGithub, `github.com` URLs). The candidate branch push works with any
  git remote.
- **One org per deployment of this intake**, set by `SELFREPAIR_AGENT_REPAIR_ORG_ID`.
- **No callback.** LangReplay polls `GET /v1/agent-repairs/{job}` and its events; SelfRepair never calls LangReplay.

## 7. Files and tests

```text
selfrepair/agent_repair/settings.py      configuration, fail closed
selfrepair/agent_repair/auth.py          bearer token + HMAC signature, org from configuration
selfrepair/agent_repair/models.py        agent_repair, agent_repair_event
selfrepair/agent_repair/store.py         the state machine, events, audit rows, the contract view
selfrepair/agent_repair/gitpilot.py      health, read-only plan, /repair through SelfRepair's GitPilot client
selfrepair/agent_repair/workspace.py     pinned clone, git apply, checks, candidate-branch push, cleanup
selfrepair/agent_repair/pipeline.py      the plan and implement steps (worker job agent_repair_step)
selfrepair/agent_repair/prs.py           the draft pull request on GitHub
selfrepair/api/routes/agent_repairs.py   the /v1/agent-repairs routes
migrations/versions/0009_agent_repair.py the two tables
tests/unit/agent_repair/                 the flow on SQLite with real git repositories, and the migration
```

The tests run the real routes, the real database layer (SQLite through aiosqlite), real git repositories and the real
checks; only GitPilot and GitHub are replaced at their boundaries, with their real answer shapes.
