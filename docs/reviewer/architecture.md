# SelfRepair Reviewer — architecture

Reviewed against the SelfRepair and GitPilot trees on 2 November 2026 (Europe/Rome).

## What already existed

- GitHub `push` and `pull_request` webhooks are verified and queued in `selfrepair/api/routes/webhooks.py`.
- Before this change, `ingest_webhook` logged those two events. CI events and issue events already had their own dispatchers.
- GitLab webhooks accepted only `Issue Hook` and `Note Hook`.
- Repair jobs, findings, and `PolicyDecision` belong to the repair state machine. A review has no repair row, so it does not reuse those tables.
- `clone_stage` is `git clone --depth=1` of the default branch with no installation token. It cannot see a push `before` SHA. Review diffs come from the GitHub compare API or a caller-supplied patch.
- GitHub App installation tokens can be minted, and `repo.github_installation_id` is now stored when a webhook carries `installation.id`. Nothing in the previous schema remembered the installation.
- SelfRepair has two GitPilot clients. `selfrepair/connectors/gitpilot.py` posts SSE to `/v1/agents/repair`, which GitPilot does not implement. The live pair is `selfrepair/coders/gitpilot_client.py` and GitPilot `POST /repair`. `POST /api/v1/gitpilot/runs` is the Matrix facade, not a review API. Remediation uses the live `/repair` body.
- GitPilot `code_inspector` is a read-only topology and can run tests. It is not the required check. The required check is produced by SelfRepair.

## What this change adds

SelfRepair owns monitoring, policy, audit, and publication. Deep Agents is an optional read-only engine. GitPilot receives an approved remediation plan and does not review its own merge.

```
push | pull_request | merge_request
        │
        ▼
ingest_* ──► reviewer.dispatcher
        │         claim delivery id (review_delivery)
        │         resolve repo by provider + name + installation
        │         merge config: defaults < org < .selfrepair.yml < API
        ▼
review_run  (org, repo, head, base, policy version) unique
        │
        ├─ DeterministicReviewEngine   always
        └─ DeepAgentsReviewEngine      only when engine: deepagents
        │
        ▼
validate lines against the diff, redact evidence, fingerprint
        │
        ▼
policy.conclude  →  success | failure | action_required | neutral
        │
        ▼
GitHub Check Run "SelfRepair / Review"
GitHub pull request review event COMMENT
GitLab commit status + MR note
```

A push and a later delivery for the same base and head share one run. Event kind is not part of the identity. A new head on the same ref marks the previous run `superseded` with conclusion `cancelled`, so an old success cannot stand in for the new commit. GitHub required checks are also per SHA.

## Engines

| Engine | When it runs | Model |
| --- | --- | --- |
| `deterministic` | Always, including when Deep Agents is selected | None |
| `deepagents` | `reviewer.engine: deepagents` and the extra is installed | OllaBridge via `ChatOpenAI` |

`deepagents` 0.7.32 (`requires-python >=3.11,<4`) is called through `create_deep_agent` with specialist subagents, `response_format=DeepAgentReport`, and filesystem permissions that allow read and deny write. No sandbox backend is attached, so the framework does not register `execute`. Snapshot tools only read the diff. If the library, `SELFREPAIR_REVIEW_MODEL`, or an OllaBridge URL (`SELFREPAIR_OLLABRIDGE_URL`, otherwise `OLLABRIDGE_BASE_URL` or `OPENAI_BASE_URL`) is missing, the engine raises `EngineUnavailable`. Deterministic findings are kept and the check conclusion is `action_required` unless a blocking finding already fails it. The worker posts the check with an installation token from `GitHubAppAuth` when the app is configured. GitLab merge requests use the compare API and a commit status plus one note.

The coordinator does not choose the check conclusion.

## Not production-ready

The Deep Agents path is integrated and bounded. It has not been measured on a live model. Do not require `SelfRepair / Review` from the Deep Agents engine until that measurement exists. The deterministic engine is the default and is what the bundled benchmark covers.
