"""Review API tenancy and the deterministic benchmark set."""
from __future__ import annotations

import uuid

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from selfrepair.config.repo_config import ReviewerConfig  # noqa: E402
from selfrepair.reviewer.diff import parse_unified_diff  # noqa: E402
from selfrepair.reviewer.engines.deterministic import DeterministicReviewEngine  # noqa: E402
from selfrepair.reviewer.schemas import DiffSet, ReviewEvent  # noqa: E402
from selfrepair.reviewer.validator import validate_findings  # noqa: E402
from tests.unit.reviewer.conftest import ORG, binding, store_with_repo  # noqa: E402

SECRET = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -0,0 +1,2 @@
+token = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"
+print(token)
"""

EVAL = """diff --git a/run.py b/run.py
--- a/run.py
+++ b/run.py
@@ -1 +1,2 @@
 def go(raw):
+    return eval(raw)
"""

CLEAN = """diff --git a/math.py b/math.py
--- a/math.py
+++ b/math.py
@@ -1 +1,2 @@
 def inc(n):
+    return n + 1
"""

PROSE = """diff --git a/notes.py b/notes.py
--- a/notes.py
+++ b/notes.py
@@ -1 +1,2 @@
+# This comment talks about eval( and a password = "notreallysecret" in prose? 
+value = 1
"""


def _labels(diff: str) -> set[str]:
    event = ReviewEvent(
        provider="github",
        kind="push",
        delivery_id="b",
        repo_full_name="octo/demo",
        branch="main",
        base_sha="a" * 40,
        head_sha="c" * 40,
    )
    parsed = DiffSet(files=parse_unified_diff(diff))
    report = DeterministicReviewEngine().review(event, parsed, ReviewerConfig())
    return {item.title for item in validate_findings(parsed, report.findings)}


def test_benchmark_deterministic_precision_and_recall() -> None:
    """Measure the bundled set. These numbers are the benchmark report."""
    secret = _labels(SECRET)
    evaluation = _labels(EVAL)
    clean = _labels(CLEAN)
    prose = _labels(PROSE)
    expected_positive = {
        "secret": {"Hard-coded credential"},
        "eval": {"Dynamic code execution"},
    }
    true_positive = int(expected_positive["secret"] <= secret) + int(
        expected_positive["eval"] <= evaluation
    )
    false_negative = 2 - true_positive
    false_positive = int(bool(clean & {"Hard-coded credential", "Dynamic code execution", "Cloud access key committed", "Private key committed"}))
    false_positive += int(
        bool(prose & {"Hard-coded credential", "Dynamic code execution", "Cloud access key committed"})
    )
    recall = true_positive / 2
    precision_denom = true_positive + false_positive
    precision = 1.0 if precision_denom == 0 else true_positive / precision_denom
    assert recall == 1.0
    assert precision == 1.0
    assert false_negative == 0
    # The prose fixture must not become a credential finding. The regex requires
    # an assignment, and the prose line is a comment that does not match it.
    assert "Hard-coded credential" not in prose


def test_review_api_is_tenant_scoped() -> None:
    store = store_with_repo()
    other = uuid.UUID("00000000-0000-0000-0000-0000000000cc")
    from selfrepair.api.main import build_app

    app = build_app()
    app.state.review_store = store
    client = TestClient(app)
    created = client.post(
        "/v1/reviews/trigger",
        headers={"X-SelfRepair-Org-Id": str(ORG)},
        json={
            "repo_full_name": "octo/demo",
            "branch": "main",
            "base_sha": "a" * 40,
            "head_sha": "b" * 40,
            "unified_diff": SECRET,
        },
    )
    assert created.status_code == 201, created.text
    review_id = created.json()["review"]["id"]
    assert created.json()["review"]["conclusion"] == "failure"
    own = client.get(f"/v1/reviews/{review_id}", headers={"X-SelfRepair-Org-Id": str(ORG)})
    assert own.status_code == 200
    foreign = client.get(
        f"/v1/reviews/{review_id}", headers={"X-SelfRepair-Org-Id": str(other)}
    )
    assert foreign.status_code == 404
    listed = client.get("/v1/reviews", headers={"X-SelfRepair-Org-Id": str(other)})
    assert listed.json()["items"] == []
    findings = client.get(
        f"/v1/reviews/{review_id}/findings", headers={"X-SelfRepair-Org-Id": str(ORG)}
    )
    assert findings.status_code == 200
    assert findings.json()["items"]
    missing = client.post(
        "/v1/reviews/trigger",
        headers={"X-SelfRepair-Org-Id": str(ORG)},
        json={
            "repo_full_name": "not/ours",
            "branch": "main",
            "base_sha": "a" * 40,
            "head_sha": "c" * 40,
        },
    )
    assert missing.status_code == 404


def test_settings_round_trip_keeps_reviews_opt_in_by_default() -> None:
    store = store_with_repo(config_yaml=None)
    from selfrepair.api.main import build_app

    app = build_app()
    app.state.review_store = store
    client = TestClient(app)
    headers = {"X-SelfRepair-Org-Id": str(ORG)}
    current = client.get(f"/v1/repos/{binding().repo_id}/review-settings", headers=headers)
    assert current.status_code == 200
    assert current.json()["config"]["enabled"] is False
    updated = client.put(
        f"/v1/repos/{binding().repo_id}/review-settings",
        headers=headers,
        json={"config": {"enabled": True, "engine": "deterministic"}},
    )
    assert updated.status_code == 200
    assert store.repo_settings[(ORG, binding().repo_id)]["enabled"] is True
    rejected = client.put(
        "/v1/review-settings",
        headers=headers,
        json={"config": {"remediation": {"auto_merge": True}}},
    )
    assert rejected.status_code == 422
