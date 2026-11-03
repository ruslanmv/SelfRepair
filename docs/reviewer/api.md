# Review API and GitPilot contract

All routes use the caller's organization from the session or `X-SelfRepair-Org-Id`. They do not accept an organization id in the body.

## Reviews

`GET /v1/reviews?repo_id=&limit=`

`GET /v1/reviews/{review_id}`

`GET /v1/reviews/{review_id}/findings`

`POST /v1/reviews/trigger`

```json
{
  "repo_full_name": "octo/demo",
  "provider": "github",
  "branch": "main",
  "base_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "head_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "unified_diff": "diff --git a/app.py b/app.py\n...",
  "pr_number": null
}
```

The manual trigger forces the deterministic engine and does not approve a pull request. The default publisher records the check payload instead of calling GitHub.

`POST /v1/reviews/{review_id}/retry` sets `queued` on an incomplete, failed, or already queued run and enqueues the Arq job `retry_review` when Redis is up. Without a queue the API re-runs the review in-process. It does not invent a success.

## Remediation

`GET /v1/reviews/{review_id}/remediations` lists the GitPilot tasks requested for one run.

`POST /v1/reviews/{review_id}/remediations`

```json
{
  "fingerprints": ["<finding fingerprint>"],
  "allowed_paths": ["app.py"],
  "approve": false
}
```

- `fingerprints` must name accepted findings of this run (1 to 50).
- `allowed_paths` defaults to the findings' files. A narrower list is allowed. A path outside those files, or an empty list, is refused.
- `approve: true` records the caller (`X-SelfRepair-Actor` or the session user) as the human approver and sends `mode: draft_pr`. Without an identified caller, or without `approve`, the task is `dry_run`.
- `auto_merge: true` is refused. So are fork pull requests, superseded runs, and repositories where `reviewer.remediation.enabled` is false. Refusals are `409` with the reason in `detail`. Another organization's run is `404`.

With Redis up the API stores the task as `queued` and enqueues Arq `remediate_review(review_id, task_id)`. The worker calls `GitPilotClient.repair` (`POST /repair`). Without a queue the API calls GitPilot directly.

The task is stored on the run under `metadata.remediations`:

| Field | Meaning |
| --- | --- |
| `id` | `review-<run>-<random>`. GitPilot works on branch `gitpilot/<id>`. |
| `status` | `queued`, `running`, `completed`, `blocked`, `needs_approval`, `failed`, `refused`, or `gitpilot_unavailable` |
| `mode` | `dry_run` or `draft_pr` |
| `plan` | The exact `POST /repair` body |
| `result` | GitPilot status, risk level, changed files, patch preview (64 KB cap), review text, `pr_url`, warnings, `stubbed` |

`gitpilot_unavailable` means `GitPilotClient` could not reach GitPilot and returned its offline stub. The stub's preview is not a patch and the task says so. No prompt, token, or raw response is stored. SelfRepair never approves, merges, or pushes; a GitPilot draft PR is a new pull request and gets its own `SelfRepair / Review` run (its branch is `gitpilot/*`, not `selfrepair/*`).

## Settings

`GET /v1/review-settings` and `PUT /v1/review-settings` store the organization default.

`GET /v1/repos/{repo_id}/review-settings` and `PUT /v1/repos/{repo_id}/review-settings` store the repository override.

`auto_merge: true` is rejected with 422.

## Check and review payloads

GitHub check:

```json
{
  "name": "SelfRepair / Review",
  "head_sha": "<head>",
  "status": "completed",
  "conclusion": "success | failure | action_required | neutral | cancelled",
  "output": { "title": "...", "summary": "...", "annotations": [] }
}
```

Annotations stop at 50. Pull request reviews use `"event": "COMMENT"` and only `RIGHT` lines that survived validation. The comment body ends with `<!-- sr-finding:<fingerprint> -->`. A fingerprint already published on that pull request is not posted again.

GitLab status uses the same context string. `success` stays `success`. `failure` and `action_required` are sent as `failed`.

## GitPilot `POST /repair`

`selfrepair.reviewer.remediation.build_repair_plan_for_findings` (and the single-finding `build_repair_plan`) returns:

```json
{
  "client_id": "selfrepair",
  "workspace_id": "<repo uuid>",
  "task_id": "review-<run>-<fingerprint prefix>",
  "repo_url": "https://github.com/octo/demo",
  "branch": "main",
  "mode": "dry_run",
  "issues": [
    {
      "id": "<fingerprint prefix>",
      "severity": "high",
      "description": "...",
      "recommended_action": "..."
    }
  ],
  "allowed_paths": ["app.py"],
  "forbidden_paths": [".env", "secrets/**", "**/*token*", "**/*secret*", "migrations/**", "infra/prod/**"],
  "coder": { "provider": "ollabridge", "model": "code-coder" },
  "sandbox": { "provider": "matrixlab", "profile": "default", "required": true },
  "human_approval": false,
  "auto_merge": false
}
```

`mode` becomes `draft_pr` only when remediation is enabled and the caller passes `human_approved=True`. `auto_merge` is always false and is not part of GitPilot's `RepairRequest` schema. `tests/unit/reviewer/test_remediation_integration.py` loads `gitpilot/repair/schema.py` from a GitPilot checkout (`GITPILOT_SRC`, or `../gitpilot`), checks that every `RepairRequest` field is present in the plan, and parses it. GitPilot also downgrades `draft_pr` to `dry_run` unless its own `GITPILOT_DRAFT_PR_ENABLED` is set. `submit_repair_plan` calls `GitPilotClient.repair` and refuses an empty allow-list or `auto_merge: true`.

`/v1/agents/repair` is not called.
