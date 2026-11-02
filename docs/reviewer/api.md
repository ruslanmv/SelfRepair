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

`POST /v1/reviews/{review_id}/retry` sets `queued` on an incomplete, failed, or already queued run. It does not invent a success.

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

`selfrepair.reviewer.remediation.build_repair_plan` returns:

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

`mode` becomes `draft_pr` only when remediation is enabled and the caller passes `human_approved=True`. `auto_merge` is always false and is not part of GitPilot's `RepairRequest` schema; the contract test strips it before `RepairRequest.from_json`. `submit_repair_plan` calls `GitPilotClient.repair` and refuses an empty allow-list or `auto_merge: true`.

`/v1/agents/repair` is not called.
