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

5. Set `SELFREPAIR_GITHUB_TOKEN` to an installation token (or a fine-scoped token) so the compare API can fetch the patch. Without it, a non-empty push is stored as an incomplete review and the check is `action_required`. The worker does not fall back to `clone_stage`.

6. For GitLab, set `GITLAB_WEBHOOK_SECRET` and subscribe to Merge Request Hooks at `POST /webhooks/gitlab`. Issue hooks are unchanged.

## Model

Deep Agents talks to OllaBridge, not to a vendor SDK directly.

```bash
export SELFREPAIR_REVIEW_MODEL=your-tool-capable-model
export SELFREPAIR_OLLABRIDGE_URL=https://ollabridge.example
export SELFREPAIR_OLLABRIDGE_API_KEY=...
```

If the model cannot do tool calls or structured output, the run ends `action_required` and the deterministic findings remain. A small local model is not assumed to be sufficient.

## Branch protection

The check name is `SelfRepair / Review`.

- GitHub: add that name as a required status check. Do not count it as a required approving review. The bot posts `COMMENT` and never `APPROVE`.
- GitLab: the commit status context is the same string. `action_required` and `failure` are published as `failed`, so a protected branch does not see a green status for an incomplete review.
- A new head SHA does not inherit the previous check. The previous run is also marked `superseded` in Postgres.

## Remediation

```bash
export GITPILOT_URL=http://gitpilot:9000
export GITPILOT_API_TOKEN=...
```

`build_repair_plan` emits the `POST /repair` body. Draft PRs require `remediation.enabled` and `human_approved=True`. The client is `selfrepair.coders.gitpilot_client.GitPilotClient`. There is no auto-merge path.

## Repository inventory

A webhook for a repository that is not in `repo` is ignored. Two organizations tracking the same `full_name` without a distinct `github_installation_id` are ignored as ambiguous. Insert the repository for the right `org_id` before enabling reviews.
