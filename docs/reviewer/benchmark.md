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
