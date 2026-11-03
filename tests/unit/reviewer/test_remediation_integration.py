"""Approved remediation through `/v1/reviews/{id}/remediations` and the worker.

GitPilot is a fake here, except for the unreachable-server case, which uses
the real `GitPilotClient` against a closed port to prove its offline stub is
recorded as `gitpilot_unavailable` and not as a patch.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from selfrepair.config.repo_config import ReviewerConfig  # noqa: E402
from selfrepair.reviewer.remediation import (  # noqa: E402
    RemediationRefused,
    build_repair_plan_for_findings,
)
from selfrepair.reviewer.schemas import FindingRecord, RunRecord  # noqa: E402
from tests.unit.reviewer.conftest import ORG, REPO, VULN_DIFF, store_with_repo  # noqa: E402

OTHER = uuid.UUID("00000000-0000-0000-0000-0000000000cc")
ENABLED_YAML = (
    "version: 1\nreviewer:\n  enabled: true\n  remediation:\n    enabled: true\n"
)


class FakeGitPilot:
    def __init__(self, payload: dict[str, Any] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.payload = payload or {
            "task_id": "t",
            "status": "ok",
            "mode": "dry_run",
            "patch_preview": "--- a/app.py\n+++ b/app.py\n",
            "changed_files": [{"path": "app.py", "change_type": "modified"}],
            "review": "looks fine",
            "risk_level": "low",
            "pr_url": None,
        }

    def repair(self, plan: dict[str, Any], dry_run: bool = True) -> Any:
        from selfrepair.coders.gitpilot_client import RepairResponse

        self.calls.append({"plan": plan, "dry_run": dry_run})
        body = dict(self.payload, mode=plan["mode"], task_id=plan["task_id"])
        return RepairResponse.from_payload(body)


class FakeQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[Any, ...]] = []

    async def enqueue_job(self, *args: Any) -> None:
        self.jobs.append(args)


def _app(store: Any, *, gitpilot: Any = None, queue: Any = None) -> TestClient:
    from selfrepair.api.main import build_app

    app = build_app()
    app.state.review_store = store
    if gitpilot is not None:
        app.state.gitpilot_client = gitpilot
    client = TestClient(app)
    # The lifespan may have set its own queue; tests decide.
    app.state.queue = queue
    return client


def _headers(org: uuid.UUID = ORG, actor: str | None = "alice") -> dict[str, str]:
    headers = {"X-SelfRepair-Org-Id": str(org)}
    if actor:
        headers["X-SelfRepair-Actor"] = actor
    return headers


def _review(client: TestClient, *, head: str = "b") -> tuple[str, list[dict[str, Any]]]:
    created = client.post(
        "/v1/reviews/trigger",
        headers=_headers(),
        json={
            "repo_full_name": "octo/demo",
            "branch": "develop",
            "base_sha": "a" * 40,
            "head_sha": head * 40,
            "unified_diff": VULN_DIFF,
            "pr_number": 7,
        },
    )
    assert created.status_code == 201, created.text
    review_id = created.json()["review"]["id"]
    findings = client.get(f"/v1/reviews/{review_id}/findings", headers=_headers()).json()["items"]
    assert findings
    return review_id, findings


def test_dry_run_without_approval_and_draft_pr_with_it() -> None:
    store = store_with_repo(config_yaml=ENABLED_YAML)
    gitpilot = FakeGitPilot()
    client = _app(store, gitpilot=gitpilot)
    review_id, findings = _review(client)
    fp = findings[0]["fingerprint"]

    dry = client.post(
        f"/v1/reviews/{review_id}/remediations",
        headers=_headers(),
        json={"fingerprints": [fp]},
    )
    assert dry.status_code == 202, dry.text
    task = dry.json()["task"]
    assert task["mode"] == "dry_run"
    assert task["status"] == "completed"
    assert task["approved"] is False
    assert gitpilot.calls[-1]["dry_run"] is True
    assert gitpilot.calls[-1]["plan"]["branch"] == "develop"
    assert gitpilot.calls[-1]["plan"]["repo_url"] == "https://github.com/octo/demo"
    assert task["result"]["changed_files"] == ["app.py"]

    # Approval with no identified human stays a dry run.
    anonymous = client.post(
        f"/v1/reviews/{review_id}/remediations",
        headers=_headers(actor=None),
        json={"fingerprints": [fp], "approve": True},
    )
    assert anonymous.json()["task"]["mode"] == "dry_run"

    approved = client.post(
        f"/v1/reviews/{review_id}/remediations",
        headers=_headers(actor="alice"),
        json={"fingerprints": [fp], "approve": True},
    )
    assert approved.status_code == 202, approved.text
    body = approved.json()["task"]
    assert body["mode"] == "draft_pr"
    assert body["approved"] is True
    assert body["requested_by"] == "alice"
    assert gitpilot.calls[-1]["dry_run"] is False
    assert gitpilot.calls[-1]["plan"]["auto_merge"] is False

    listed = client.get(f"/v1/reviews/{review_id}/remediations", headers=_headers())
    assert {item["mode"] for item in listed.json()["items"]} == {"dry_run", "draft_pr"}
    stored = json.dumps(store.runs[uuid.UUID(review_id)].metadata)
    assert "Authorization" not in stored
    assert "Bearer" not in stored
    task_keys = set(store.runs[uuid.UUID(review_id)].metadata["remediations"][0])
    assert not {key for key in task_keys if "token" in key or "prompt" in key}
    assert "raw" not in store.runs[uuid.UUID(review_id)].metadata["remediations"][0]["result"]


def test_remediation_refusals() -> None:
    store = store_with_repo(config_yaml=ENABLED_YAML)
    gitpilot = FakeGitPilot()
    client = _app(store, gitpilot=gitpilot)
    review_id, findings = _review(client)
    fp = findings[0]["fingerprint"]
    url = f"/v1/reviews/{review_id}/remediations"

    empty = client.post(url, headers=_headers(), json={"fingerprints": [fp], "allowed_paths": []})
    assert empty.status_code == 409
    assert "allowed_paths" in empty.json()["detail"]
    outside = client.post(
        url, headers=_headers(), json={"fingerprints": [fp], "allowed_paths": ["other.py"]}
    )
    assert outside.status_code == 409
    merge = client.post(url, headers=_headers(), json={"fingerprints": [fp], "auto_merge": True})
    assert merge.status_code == 409
    unknown = client.post(url, headers=_headers(), json={"fingerprints": ["f" * 64]})
    assert unknown.status_code == 409
    none = client.post(url, headers=_headers(), json={"fingerprints": []})
    assert none.status_code == 422
    foreign = client.post(url, headers=_headers(OTHER), json={"fingerprints": [fp]})
    assert foreign.status_code == 404
    foreign_list = client.get(url, headers=_headers(OTHER))
    assert foreign_list.status_code == 404
    assert gitpilot.calls == []


def test_fork_pull_request_is_refused() -> None:
    store = store_with_repo(config_yaml=ENABLED_YAML)
    gitpilot = FakeGitPilot()
    client = _app(store, gitpilot=gitpilot)
    review_id, findings = _review(client)
    run = store.runs[uuid.UUID(review_id)]
    store.runs[run.id] = run.model_copy(update={"from_fork": True})
    refused = client.post(
        f"/v1/reviews/{review_id}/remediations",
        headers=_headers(),
        json={"fingerprints": [findings[0]["fingerprint"]], "approve": True},
    )
    assert refused.status_code == 409
    assert "fork" in refused.json()["detail"]
    assert gitpilot.calls == []


def test_disabled_remediation_is_refused() -> None:
    store = store_with_repo()  # reviewer enabled, remediation default off
    client = _app(store, gitpilot=FakeGitPilot())
    review_id, findings = _review(client)
    refused = client.post(
        f"/v1/reviews/{review_id}/remediations",
        headers=_headers(),
        json={"fingerprints": [findings[0]["fingerprint"]]},
    )
    assert refused.status_code == 409
    assert refused.json()["detail"] == "remediation disabled"


def test_unreachable_gitpilot_is_not_a_patch() -> None:
    from selfrepair.coders.gitpilot_client import GitPilotClient

    store = store_with_repo(config_yaml=ENABLED_YAML)
    client = _app(store, gitpilot=GitPilotClient("http://127.0.0.1:9", timeout=2))
    review_id, findings = _review(client)
    resp = client.post(
        f"/v1/reviews/{review_id}/remediations",
        headers=_headers(),
        json={"fingerprints": [findings[0]["fingerprint"]], "approve": True},
    )
    assert resp.status_code == 202, resp.text
    task = resp.json()["task"]
    assert task["status"] == "gitpilot_unavailable"
    assert task["result"]["stubbed"] is True
    assert "no patch" in task["error"]


async def test_queued_remediation_runs_on_the_worker() -> None:
    from selfrepair.worker.main import remediate_review

    store = store_with_repo(config_yaml=ENABLED_YAML)
    queue = FakeQueue()
    client = _app(store, queue=queue)
    review_id, findings = _review(client)
    resp = client.post(
        f"/v1/reviews/{review_id}/remediations",
        headers=_headers(),
        json={"fingerprints": [findings[0]["fingerprint"]], "approve": True},
    )
    assert resp.status_code == 202
    assert resp.json()["outcome"] == "queued"
    name, job_review, task_id = queue.jobs[-1]
    assert name == "remediate_review" and job_review == review_id
    gitpilot = FakeGitPilot()
    outcome = await remediate_review(
        {"review_store": store, "gitpilot_client": gitpilot}, review_id, task_id
    )
    assert outcome == "completed"
    assert gitpilot.calls[0]["plan"]["mode"] == "draft_pr"
    # A second delivery of the same job does not resubmit a completed task.
    again = await remediate_review(
        {"review_store": store, "gitpilot_client": gitpilot}, review_id, task_id
    )
    assert again == "completed"
    assert len(gitpilot.calls) == 1


def test_retry_with_a_queue_enqueues_the_worker_job() -> None:
    store = store_with_repo()
    queue = FakeQueue()
    client = _app(store, queue=queue)
    review_id, _ = _review(client)
    run = store.runs[uuid.UUID(review_id)]
    store.runs[run.id] = run.model_copy(update={"status": "incomplete"})
    resp = client.post(f"/v1/reviews/{review_id}/retry", headers=_headers())
    assert resp.status_code == 202
    assert resp.json()["outcome"] == "queued"
    assert queue.jobs[-1] == ("retry_review", review_id)
    assert store.runs[run.id].status == "queued"


def test_gitlab_merge_request_passes_the_event_uuid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITLAB_WEBHOOK_SECRET", "s3cret")
    queue = FakeQueue()
    client = _app(store_with_repo(), queue=queue)
    resp = client.post(
        "/webhooks/gitlab",
        headers={
            "X-Gitlab-Event": "Merge Request Hook",
            "X-Gitlab-Token": "s3cret",
            "X-Gitlab-Event-UUID": "abc-123",
        },
        json={"object_attributes": {"id": 1}},
    )
    assert resp.status_code == 200, resp.text
    assert queue.jobs[-1][0] == "ingest_gitlab_webhook"
    assert queue.jobs[-1][3] == "gitlab:abc-123"
    issue = client.post(
        "/webhooks/gitlab",
        headers={
            "X-Gitlab-Event": "Issue Hook",
            "X-Gitlab-Token": "s3cret",
            "X-Gitlab-Event-UUID": "abc-124",
        },
        json={},
    )
    assert issue.status_code == 200
    assert len(queue.jobs[-1]) == 3


# --- live GitPilot schema contract -------------------------------------------


def _gitpilot_schema() -> Any:
    cached = sys.modules.get("_gitpilot_repair_schema")
    if cached is not None:
        return cached
    candidates = [
        os.getenv("GITPILOT_SRC", ""),
        str(Path(__file__).resolve().parents[4] / "gitpilot"),
        "/agent/repos/gitpilot",
    ]
    for root in candidates:
        path = Path(root) / "gitpilot" / "repair" / "schema.py" if root else None
        if path is not None and path.exists():
            # Load the module file alone so GitPilot's package import does not
            # pull its server dependencies into this test process.
            spec = importlib.util.spec_from_file_location("_gitpilot_repair_schema", path)
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module  # postponed annotations resolve here
            spec.loader.exec_module(module)
            return module
    pytest.skip("gitpilot checkout not found (set GITPILOT_SRC)")


def _finding(fp: str, path: str, severity: str = "high") -> FindingRecord:
    return FindingRecord(
        fingerprint=fp * 64,
        category="security",
        severity=severity,  # type: ignore[arg-type]
        file_path=path,
        start_line=2,
        title="Dynamic eval",
        description="eval of request input",
        suggested_fix="use ast.literal_eval",
        source="deterministic",
    )


def test_multi_finding_plan_parses_with_the_live_repair_request() -> None:
    schema = _gitpilot_schema()
    run = RunRecord(
        id=uuid.uuid4(),
        org_id=ORG,
        repo_id=REPO,
        provider="github",
        event_type="pull_request",
        base_sha="a" * 40,
        head_sha="b" * 40,
        engine="deterministic",
        policy_version="1",
        status="completed",
        metadata={"repo_full_name": "octo/demo", "branch": "develop"},
    )
    config = ReviewerConfig.model_validate({"remediation": {"enabled": True}})
    plan = build_repair_plan_for_findings(
        run=run,
        findings=[_finding("a", "app.py"), _finding("b", "lib/util.py", "info")],
        repo_url="https://github.com/octo/demo",
        config=config,
        human_approved=True,
        base_branch="develop",
    )
    # Every field RepairRequest declares is present: nothing it needs is stripped.
    declared = set(schema.RepairRequest.model_fields)
    assert declared <= set(plan), declared - set(plan)
    owned = {key: value for key, value in plan.items() if key in declared}
    parsed = schema.RepairRequest.from_json(owned)
    assert parsed.mode == schema.RepairMode.draft_pr
    assert parsed.allowed_paths == ["app.py", "lib/util.py"]
    assert parsed.branch == "develop"
    assert [issue.severity.value for issue in parsed.issues] == ["high", "medium"]
    assert parsed.sandbox.required is True
    # The only extra key is the explicit merge refusal, and it is false.
    assert set(plan) - declared == {"auto_merge"}
    assert plan["auto_merge"] is False
    # GitPilot ignores unknown keys, so the full plan parses as sent over HTTP.
    assert schema.RepairRequest.from_json(plan).allowed_paths == ["app.py", "lib/util.py"]

    with pytest.raises(RemediationRefused):
        build_repair_plan_for_findings(
            run=run,
            findings=[_finding("a", "app.py")],
            repo_url="https://github.com/octo/demo",
            config=config,
            human_approved=False,
            allowed_paths=["app.py", "../etc/passwd"],
        )
