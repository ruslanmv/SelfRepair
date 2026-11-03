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

## Deep Agents: not measured

Recall, precision, citation validity, latency, and cost for `engine: deepagents` were **not measured**. As of 3 November 2026 no OllaBridge endpoint, model, or API key was available to the integration run. With `deepagents` 0.7.32, `langchain-openai` 1.7.3, and `langgraph` 1.2.19 installed, `test_deepagents_and_remediation.py::test_harness_builds_on_installed_deepagents` passed: the `create_deep_agent` graph builds and cannot write. That test makes no model call. Do not require `SelfRepair / Review` from the Deep Agents engine on the strength of this document.

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
