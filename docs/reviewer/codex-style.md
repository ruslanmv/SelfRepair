# Codex-style pull-request review

SelfRepair reviews pull requests the way developers know from hosted AI
reviewers. SelfRepair owns the GitHub App, triggers, policy and publication.
The model review runs through any OpenAI-compatible endpoint (OllaBridge Cloud
by default). GitPilot writes fixes, and only when a maintainer asks.

## What appears on a pull request

| When | What |
| --- | --- |
| Review starts | 👀 on the pull request (or on the `@selfrepair review` comment). The status comment gets a `🔄 In progress` row. The `SelfRepair / Review` check is `in_progress`. |
| Review ends | The status comment row becomes `✅ Completed` / `⚠️ Incomplete` / `❌ Failed`. The check completes. A **💡 SelfRepair Review** names the reviewed commit and carries inline suggestions. |
| Clean commit | "Didn't find any major issues. 🚀" and 👍 on the pull request. |
| Re-review, nothing new | Only the check and status comment change; suggestions already posted are not repeated. |

Status comment (one per pull request, edited in place, last five rows):

```
### SelfRepair Review Summary
| Review | Status | Commit | Review trigger |
| 📝 Code Review | ✅ Completed 2026-11-13 10:02 UTC | `af3a4d7` | PR opened |
```

Inline suggestion:

```
**<sub><sub>![P2 Badge](https://img.shields.io/badge/P2-yellow?style=flat)</sub></sub>  Allow the configuration form to shrink and scroll**

On short viewports … Make the form a shrinkable flex column …

Useful? React with 👍 / 👎.
```

Priorities map from severity: critical → P0, high → P1, medium → P2,
low/info → P3. `reviewer.review.min_inline_priority` (default `P2`) sets the
lowest priority posted inline; lower ones are listed in the review body and
always reach the check.

## Commands

| Comment on a pull request | Effect |
| --- | --- |
| `@selfrepair review` | Review the latest head again (drafts included). |
| `@selfrepair fix` / `@selfrepair address …` | Send the open suggestions of the latest review to GitPilot `POST /repair` in `draft_pr` mode, approved by the commenter. Requires `reviewer.remediation.enabled`. Forks are refused. |

Handles: `reviewer.mentions.handles` (default `selfrepair`, `gitpilot`).
Only `reviewer.mentions.allowed_associations` (default OWNER, MEMBER,
COLLABORATOR) are obeyed. Bot comments, quoted lines and code blocks are ignored.

## Engine `llm`

`reviewer.engine: llm` with `SELFREPAIR_REVIEW_LLM_URL`,
`SELFREPAIR_REVIEW_MODEL` and `SELFREPAIR_REVIEW_LLM_KEY`.

- The diff is redacted (`selfrepair.ci.redaction`) and rendered with new-file
  line numbers, so citations are exact.
- The prompt asks only for discrete, actionable bugs introduced by the diff,
  P0–P3, JSON only; repository text is declared untrusted.
- Findings below 0.55 confidence, on files outside the diff, or on lines the
  diff does not contain are dropped (the latter by the validator).
- Large diffs are split by file (60k characters per call, at most 6 calls,
  within `execution.max_runtime_seconds`); anything unreviewed makes the run
  incomplete rather than passing.
- No key, a refused key, or a bad reply raises `EngineUnavailable`: the
  deterministic findings are kept and the check is not a pass.

## Hugging Face development edition

`selfrepair.reviewer.space_app` runs the reviewer in one process with an
in-memory store. See `deploy/huggingface-review/README.md` for the Space and the
token-protected GitHub App manifest setup.
