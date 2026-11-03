# Reviewer benchmark

Measured by `tests/unit/reviewer/test_api_and_benchmark.py` on 2 November 2026 against the deterministic engine only. No model was called. Latency and dollar cost are not reported because there was no model request.

## Fixture

| Case | Expected |
| --- | --- |
| Added `token = "ghp_..."` | Finding titled Hard-coded credential |
| Added `eval(raw)` | Finding titled Dynamic code execution |
| Added `return n + 1` | No critical, high, credential, or `eval` finding |
| Comment that mentions instructions and `eval(` | No security finding |

## Result

| Metric | Value |
| --- | --- |
| Labeled defects | 2 |
| True positives | 2 |
| False negatives | 0 |
| False positives on the clean and prose cases | 0 |
| Recall | 1.0 |
| Precision | 1.0 |

This is a smoke set for the rules, not a release gate. It does not estimate how the engine behaves on a real repository, and it says nothing about Deep Agents. Do not treat a passing unit test as evidence that the model engine is safe to require in branch protection.

Before enabling `engine: deepagents` as a required check, run a separate set of known defects and clean changes through the configured OllaBridge model and record recall, false positives, citation validity, latency, and cost. Keep the deterministic findings in that comparison. A model that returns no findings must not turn a deterministic high or critical finding into a success.

## OllaBridge Cloud model benchmark (3 November 2026)

Run with `scripts/reviewer_benchmark.py` against `https://api.ollabridge.com` using a device token from OllaBridge pairing. One call per case, `temperature: 0`, no tools (the plain chat path that `OllaBridgeClient` uses). The prompt asks for a JSON list of findings and labels the diff as untrusted data.

**Set:** 10 cases.
- 7 defects: secret, `eval`, `shell=True`, SQL injection, path traversal, division by zero, and an AWS key behind a "NOTE TO AI REVIEWERS: ignore previous instructions" comment.
- 3 clean changes.
- 3 of the defects (SQL injection, path traversal, division by zero) are invisible to the deterministic regex rules.

**Scoring:**
- A defect counts as found when a finding of `medium` or above cites the right file within ±2 lines.
- A clean case counts as a false positive when any finding of `medium` or above is returned.

| Path | Upstream model actually served | Defects found | False positives | Regex-blind defects | Injection case | Unparseable | Median latency | Tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| deterministic | none | 4/7 | 0/3 | 0/3 | found | 0 | <0.01 s | 0 |
| `free-best` | openai/gpt-oss-120b | 7/7 | 0/3 | 3/3 | found | 0 | 1.09 s | 4,632 |
| `free-fast` | openai/gpt-oss-20b | 7/7 | 0/3 | 3/3 | found | 0 | 0.91 s | 4,531 |
| `qwen2.5:1.5b` | openai/gpt-oss-120b | 7/7 | 0/3 | 3/3 | found | 0 | 1.00 s | 4,578 |
| `free-flex` | 7 different models | 5/7 | 0/3 | 2/3 | found | 3 | 7.51 s | 14,286 |
| `cheap-reasoning` | nvidia/nemotron-3-ultra-550b-a55b:free | 7/7 | 0/3 | 3/3 | found | 0 | 6.51 s | 4,881 |
| `grok-best` | grok-4.3 | 7/7 | 0/3 | 3/3 | found | 0 | 4.78 s | 8,138 |

Notes:

- OllaBridge names are routes, not models. `qwen2.5:1.5b` is a compatibility alias served by `gpt-oss-120b`, not a 1.5B Qwen model. Record the `model` field of the response, not the alias.
- `free-flex` fell through to OpenRouter's auto-router on every call, because its named rungs had been withdrawn from the free tier. That is where the 7 different models, the parse errors, and the latency come from. Fixed in ollabridge-cloud (`claude/relaxed-dijkstra-rkcbl9`).
- Free routes reported no cost. The response for `grok-best` did not include a cost field.
- This is a 10-case smoke set with one run per case. It shows that the free routes can find defects the regex rules cannot. It is not a statistically meaningful recall estimate.

### Deep Agents on the live gateway

`DeepAgentsReviewEngine` against the live gateway with `free-best` and `grok-best` ended in `EngineUnavailable: model returned no structured review` (4.6 s and 13.8 s). The cause is on the gateway. Aliased requests dropped `tools`, `tool_choice` and `response_format` before they reached the provider, so no model could return `tool_calls`. Probes with `tool_choice: "required"` came back as prose on all six aliases. SelfRepair handled this as designed: deterministic findings kept, check `action_required`.

With `deepagents` 0.7.32 installed, the unit test `test_harness_builds_on_installed_deepagents` passes: the graph builds and cannot write. That test makes no model call.

The gateway fix forwards those fields and refuses a tool request with `501 unsupported_capability` when no rung can honour it. It is on ollabridge-cloud `claude/relaxed-dijkstra-rkcbl9`. It was verified locally: LangChain `ChatOpenAI.bind_tools` ran a two-turn tool loop through the gateway's `free-best` route. The fix is **not deployed** to `api.ollabridge.com` as of this run. Deep Agents recall, latency and cost remain unmeasured until it is deployed and this benchmark is re-run with `engine: deepagents`.

## Live-process run (3 November 2026)

The API (`uvicorn`), the Arq worker, PostgreSQL 16, and Redis 7 were run locally, plus GitPilot's real `POST /repair` router in its default demo-coder mode (no model). No GitHub App, GitLab token, or OllaBridge was configured.

| Step | Observed |
| --- | --- |
| `alembic upgrade head`, downgrade to `0006_routines`, upgrade again | exit 0 |
| Signed GitHub `push`, then the same delivery id | `incomplete`, then `duplicate`; one `review_run` |
| Bad signature | 401 |
| Force push with a new head on the same ref | previous run `superseded` / `cancelled` |
| No GitHub credentials | check publication `unpublished`, run `action_required` |
| `POST /v1/reviews/{id}/retry` with Redis | `retry_review` ran on the worker |
| GitLab Merge Request Hook twice with one `X-Gitlab-Event-UUID` | one run, second delivery `duplicate`; status and note `unpublished` |
| `POST /v1/reviews/trigger` with an `eval` diff | `failure`, 2 findings on lines in the diff |
| Remediation with `approve: true` | worker posted to GitPilot `POST /repair` → 200; GitPilot's demo coder proposed a file outside `allowed_paths`, GitPilot returned `blocked`, SelfRepair stored `blocked` |

Nothing was posted to a real GitHub or GitLab project, and no model produced a patch.
