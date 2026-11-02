# Reviewer security

## Permissions

| Actor | Can read the diff | Can write the repo | Can approve or merge |
| --- | --- | --- | --- |
| Deterministic engine | Yes, added lines only | No | No |
| Deep Agents harness | Diff snapshot tools, filesystem reads denied for writes | No `execute` backend, write permission denied | No |
| GitHub publisher | Installation token | Check runs and `COMMENT` reviews | Never `APPROVE` |
| GitPilot remediation | Repair plan with `allowed_paths` | Draft PR only after human approval | `auto_merge` is rejected by the schema |

Review agents do not receive the GitHub token. The publisher holds it. Prompts are redacted with the CI redaction rules before they are stored. Evidence stored on `review_finding` is redacted. Webhook signatures are unchanged: GitHub HMAC and GitLab token.

## Isolation

- Tenant lookup is `(provider, full_name, installation id)`. An ambiguous match does not pick an organization.
- API reads filter on `CtxDep.org_id`. Another organization's review id returns 404.
- Snapshot tools reject absolute paths, `~`, and `..`.
- Remediation rejects fork pull requests, paths containing `..`, empty `allowed_paths`, and `auto_merge: true`.
- `selfrepair/` branches and the SelfRepair bot sender are not reviewed, so a repair push cannot enqueue another review of itself.
- Repository text is labeled untrusted in the Deep Agents system prompt. A comment that says to ignore policy does not remove a deterministic secret finding, and the policy function does not read the model summary when deciding `failure`.
- The deterministic rules skip comment lines so a sentence about `eval(` is not a finding.
- Untrusted tests are not executed on the API host. `sandbox.required` is set on remediation plans. Review itself does not run repository commands.

## Failure behavior

A missing diff, a truncated diff, a model timeout, or an unavailable engine finishes as `action_required` or, when a blocking deterministic finding exists, `failure`. Neither path reports `success`. Transient GitHub 429 responses raise `TransientReviewError` so Arq can retry the same job (`job_try` > 1 is allowed past the delivery claim).

## Publication

The worker mints `GitHubAppAuth.installation_token` when `GITHUB_APP_ID` and a private key are set and the repository has an installation id. `SELFREPAIR_GITHUB_TOKEN` is only the fallback. A missing credential is stored as `unpublished` and a clean review is `action_required`, not a green check. Pull-request diffs come from the base repository's files API, so a fork is not cloned.

## Threats not closed here

- A live model can still produce a plausible, wrong comment on a line that is in the diff. Line checks stop fabricated locations; they do not stop a wrong explanation of a real line.
- GitLab line discussions are a single note plus a commit status, not a per-line discussion thread.
- The bundled benchmark does not measure Deep Agents.
- Unit tests use fake HTTP transports. They do not prove a live GitHub, GitLab, or OllaBridge call.
