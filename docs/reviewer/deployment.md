# Reviewer deployment

## Process

1. Install SelfRepair with the server extra. Add the reviewer extra only when Deep Agents should be importable:

   ```bash
   pip install -e '.[server]'
   pip install -e '.[reviewer]'   # optional, deepagents>=0.7.32,<0.8
   ```

2. Apply migrations. `0007_reviewer` adds review tables and `repo.github_installation_id`.

   ```bash
   alembic upgrade head
   ```

3. Run the API and the Arq worker:

   ```bash
   arq selfrepair.worker.main.WorkerSettings
   ```

4. Point the GitHub App webhook at `POST /webhooks/github` with `GITHUB_WEBHOOK_SECRET`. Subscribe to `push` and `pull_request`. The app needs contents read, pull requests write, and checks write on the installation before publication can succeed. Metadata read is required for compare.

5. Give the API and the worker the GitHub App credentials so each review mints an installation token:

   ```bash
   export GITHUB_APP_ID=123456
   export GITHUB_APP_PRIVATE_KEY="$(cat /run/secrets/github-app.pem)"
   ```

   `SELFREPAIR_GITHUB_TOKEN`, then `GITHUB_TOKEN`, is accepted when the app is not configured. Do not leave an unrelated `GITHUB_TOKEN` in the worker environment: the worker will use it to read diffs and post checks. Without either credential, a non-empty push is stored as an incomplete review and nothing is posted to GitHub. The worker does not fall back to `clone_stage`. Every diff, pull requests included, comes from the revision-pinned compare API (`base_sha...head_sha`) on the base repository; fork PR commits are reachable there by SHA. Only if compare returns 404 does the worker use the pull-request files API, and only after confirming the PR head is still the event's head; if it moved, the run stays incomplete and the newer head's own event reviews it. The worker posts `SelfRepair / Review` as `in_progress` before analysis and then updates that same check run to its final conclusion. If the review fails or hits a transient error, the check is completed as `action_required`, so no check stays `in_progress`. `retry_review` is an Arq job; `POST /v1/reviews/{id}/retry` enqueues it when Redis is up.

6. For GitLab, set `GITLAB_WEBHOOK_SECRET` (or `SELFREPAIR_GITLAB_WEBHOOK_SECRET`) and subscribe to Merge Request Hooks at `POST /webhooks/gitlab`. Issue hooks are unchanged. The API forwards `X-Gitlab-Event-UUID` to the worker as the delivery id for merge requests, so a redelivery is `duplicate`. GitHub accepts `GITHUB_WEBHOOK_SECRET` or `SELFREPAIR_GITHUB_WEBHOOK_SECRET`.

## Model

Deep Agents talks to OllaBridge, not to a vendor SDK directly.

```bash
export SELFREPAIR_REVIEW_MODEL=your-tool-capable-model
export SELFREPAIR_OLLABRIDGE_URL=https://ollabridge.example
export SELFREPAIR_OLLABRIDGE_API_KEY=...
```

If the model cannot do tool calls or structured output, the run ends `action_required` and the deterministic findings remain. A small local model is not assumed to be sufficient.

OllaBridge model names are routes. `qwen2.5:1.5b` on OllaBridge Cloud is served by `gpt-oss-120b`. `free-fast` and `free-best` gave the best speed and accuracy in `benchmark.md`. Deep Agents needs the gateway to forward `tools`: see the benchmark notes for the gateway version that does.

## Branch protection

The check name is `SelfRepair / Review`.

- GitHub: add that name as a required status check. Do not count it as a required approving review. The bot posts `COMMENT` and never `APPROVE`.
- GitLab: the commit status context is the same string. `action_required` and `failure` are published as `failed`, so a protected branch does not see a green status for an incomplete review.
- A new head SHA does not inherit the previous check. The previous run is also marked `superseded` in Postgres.

## Remediation

```bash
export SELFREPAIR_GITPILOT_URL=http://gitpilot:8000   # or GITPILOT_URL
export SELFREPAIR_GITPILOT_TOKEN=...                  # or GITPILOT_API_TOKEN
```

Compose passes these to both the API and the worker. Tasks are created with `POST /v1/reviews/{id}/remediations` and run on the worker as `remediate_review`. Draft PRs require `remediation.enabled`, an identified caller, and `approve: true`; GitPilot must also have `GITPILOT_DRAFT_PR_ENABLED`. The client is `selfrepair.coders.gitpilot_client.GitPilotClient`. There is no auto-merge path.

## Console

The console has a **Reviews** page: run list, run detail with findings, retry for incomplete runs, a per-finding GitPilot dry run, the remediation task list, and the organization default settings.

## Verifying the database

```bash
SELFREPAIR_TEST_DATABASE_URL=postgresql+psycopg://postgres@localhost:5432/postgres \
  python -m pytest tests/integration/test_review_postgres.py
```

The test creates a throwaway database, runs `alembic upgrade head`, round-trips a run, findings, a publication, supersession, settings, and remediation metadata through `SqlReviewStore`, downgrades to `0006_routines`, upgrades again, and drops the database. It is skipped when the variable is unset.

## Repository inventory

A webhook for a repository that is not in `repo` is ignored. Two organizations tracking the same `full_name` without a distinct `github_installation_id` are ignored as ambiguous. Insert the repository for the right `org_id` before enabling reviews.
