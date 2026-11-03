# Reviewer security

## Permissions

| Actor | Can read the diff | Can write the repo | Can approve or merge |
| --- | --- | --- | --- |
| Deterministic engine | Yes, added lines only | No | No |
| Deep Agents harness | Diff snapshot tools, filesystem reads denied for writes | No `execute` backend, write permission denied | No |
| GitHub publisher | Installation token | Check runs and `COMMENT` reviews | Never `APPROVE` |
| GitPilot remediation | Repair plan with `allowed_paths` | Draft PR only after human approval | `auto_merge` is rejected by the schema |

Review agents do not receive the GitHub token. The publisher holds it. Prompts are redacted with the CI redaction rules before they are stored. The Deep Agents snapshot tools (`read_snapshot`, `search_snapshot`) read and search the same redacted text, so a tool call cannot return a committed credential to the model provider or confirm one by guessing. Evidence stored on `review_finding` is redacted. Webhook signatures are unchanged: GitHub HMAC and GitLab token.

## Isolation

- Tenant lookup is `(provider, full_name, installation id)`. An ambiguous match does not pick an organization.
- API reads filter on `CtxDep.org_id`. Another organization's review id returns 404.
- Snapshot tools reject absolute paths, `~`, and `..`.
- Remediation rejects fork pull requests, paths containing `..` or starting with `/`, empty `allowed_paths`, paths outside the selected findings' files, findings from another run, superseded runs, and `auto_merge: true`. It is tenant-scoped through the run's `org_id`. Approval (`draft_pr`) needs an identified caller; anything else is `dry_run`.
- The remediation record stores the plan and GitPilot's parsed result. It does not store prompts, tokens, or the raw response. An offline GitPilot stub is stored as `gitpilot_unavailable`, not as a patch.
- `selfrepair/` branches and the SelfRepair bot sender are not reviewed, so a repair push cannot enqueue another review of itself.
- Repository text is labeled untrusted in the Deep Agents system prompt. A comment that says to ignore policy does not remove a deterministic secret finding, and the policy function does not read the model summary when deciding `failure`.
- The deterministic rules skip comment lines so a sentence about `eval(` is not a finding.
- Untrusted tests are not executed on the API host. `sandbox.required` is set on remediation plans. Review itself does not run repository commands.

## Failure behavior

A missing diff, a truncated diff, a model timeout, or an unavailable engine finishes as `action_required` or, when a blocking deterministic finding exists, `failure`. Neither path reports `success`. Transient GitHub 429 responses raise `TransientReviewError` so Arq can retry the same job (`job_try` > 1 is allowed past the delivery claim).

## Publication

The worker mints `GitHubAppAuth.installation_token` when `GITHUB_APP_ID` and a private key are set and the repository has an installation id. `SELFREPAIR_GITHUB_TOKEN` is only the fallback. A missing credential is stored as `unpublished` and a clean review is `action_required`, not a green check. Pull-request diffs come from the base repository's compare API pinned to the event's SHAs, so a fork is not cloned and a finding is never stored under a revision it was not computed from.

## Threats not closed here

- A live model can still produce a plausible, wrong comment on a line that is in the diff. Line checks stop fabricated locations; they do not stop a wrong explanation of a real line.
- GitLab line discussions are a single note plus a commit status, not a per-line discussion thread.
- The bundled benchmark does not measure Deep Agents.
- Unit tests use fake HTTP transports. They do not prove a live GitHub, GitLab, or OllaBridge call. See `benchmark.md` for what was run against live processes.
