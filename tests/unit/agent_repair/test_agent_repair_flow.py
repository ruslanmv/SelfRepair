"""Agent repair end to end inside SelfRepair: signed intake, read-only plan, enforced approval and scope,
the patch on the pinned base commit with static checks, cancellation, bounded retries, and a draft PR.
Real SQLite database, real git; GitPilot replaced at its boundary with its real answer shapes."""

from __future__ import annotations

import json
import time
import uuid

import pytest
from sqlalchemy import select

from selfrepair.agent_repair.models import AgentRepair
from selfrepair.agent_repair.pipeline import run_step
from selfrepair.api.routes import agent_repairs as routes
from selfrepair.persistence.models import AuditLog


def create_body(w, attempt="rep-1", **over):
    ev = w.evidence()
    body = {"source": "langreplay", "attempt_id": attempt, "case_id": "ebook-return-wrong-format", "evidence_id": ev["evidence_id"],
            "evidence": ev, "repository": {"url": w.repo.url, "base_commit": w.repo.base, "ref": "main"}, "mode": "plan",
            "requested_by": "jordan"}
    body.update(over)
    return body


async def planned(w):
    res = await w.signed.post("/v1/agent-repairs", create_body(w), key="rep-1:plan")
    job = res.json()["job_id"]
    assert await run_step(w.sessionmaker, uuid.UUID(job), "plan", w.gitpilot.deps()) == "plan_ready"
    return job


async def implemented(w, job, scope=("agent.py",)):
    res = await w.signed.post(f"/v1/agent-repairs/{job}/approve", {"approved_by": "jordan", "what": "plan", "scope": list(scope), "plan_sha256": "sha256:p"})
    assert res.status_code == 200, res.text
    return await run_step(w.sessionmaker, uuid.UUID(job), "implement", w.gitpilot.deps())


async def audit_actions(w):
    async with w.sessionmaker() as s:
        return [r.action for r in (await s.execute(select(AuditLog).order_by(AuditLog.id))).scalars()]


async def test_it_fails_closed_without_configuration_and_refuses_bad_credentials(world, monkeypatch):
    w = world
    assert (await w.signed.post("/v1/agent-repairs", create_body(w))).status_code == 202
    bad_token = type(w.signed)(w.client, token="wrong")
    assert (await bad_token.post("/v1/agent-repairs", create_body(w, "rep-2"))).status_code == 401
    bad_secret = type(w.signed)(w.client, secret="wrong")
    assert (await bad_secret.post("/v1/agent-repairs", create_body(w, "rep-2"))).status_code == 401
    stale = await w.signed.post("/v1/agent-repairs", create_body(w, "rep-2"), ts=int(time.time()) - 3600)
    assert stale.status_code == 401 and "too old" in stale.json()["detail"]
    body = json.dumps(create_body(w, "rep-2")).encode()
    tampered = await w.client.post("/v1/agent-repairs", content=body.replace(b"jordan", b"mallory"), headers=w.signed.headers(body))
    assert tampered.status_code == 401 and "signature" in tampered.json()["detail"]
    monkeypatch.delenv("SELFREPAIR_AGENT_REPAIR_REPOS")
    off = await w.signed.post("/v1/agent-repairs", create_body(w, "rep-3"))
    assert off.status_code == 503 and "not enabled" in off.json()["detail"]


async def test_intake_checks_the_repository_and_the_evidence_and_is_idempotent(world):
    w = world
    other = await w.signed.post("/v1/agent-repairs", create_body(w, repository={"url": "https://github.com/evil/repo", "base_commit": w.repo.base}))
    assert other.status_code == 403
    ev = w.evidence()
    ev["failure"]["first_message"] = "changed after hashing"
    forged = await w.signed.post("/v1/agent-repairs", create_body(w, evidence=ev))
    assert forged.status_code == 400 and "does not match" in forged.json()["detail"]
    short = await w.signed.post("/v1/agent-repairs", create_body(w, repository={"url": w.repo.url, "base_commit": "main"}))
    assert short.status_code == 422                                                    # a branch name is not a pinned commit
    first = await w.signed.post("/v1/agent-repairs", create_body(w), key="rep-1:plan")
    assert first.status_code == 202 and first.json()["state"] == "planning"
    assert w.queue.jobs == [("agent_repair_step", first.json()["job_id"], "plan")]
    again = await w.signed.post("/v1/agent-repairs", create_body(w))
    assert again.json()["job_id"] == first.json()["job_id"] and len(w.queue.jobs) == 1
    assert await audit_actions(w) == ["agent_repair.create"]
    async with w.sessionmaker() as s:
        row = (await s.execute(select(AgentRepair))).scalar_one()
        assert row.org_id == w.org and row.base_commit == w.repo.base and row.requested_by == "jordan"


async def test_the_plan_is_read_only_and_a_demo_coder_is_refused(world):
    w = world
    job = await planned(w)
    status = (await w.signed.get(f"/v1/agent-repairs/{job}")).json()
    assert status["state"] == "plan_ready" and status["plan"]["files"] == ["agent.py"]
    assert any("execute" in r for r in status["plan"]["risks"]) and "make test" not in status["plan"]["files"]
    assert status["coder"] == {"agent": "gitpilot", "version": "0.2.8", "provider": "ollabridge", "model": "code-coder", "demo": False}
    assert [c[0] for c in w.gitpilot.calls] == ["health", "plan"]                       # no /repair before approval
    assert status["patch"] is None
    w.gitpilot.demo = True
    res = await w.signed.post("/v1/agent-repairs", create_body(w, "rep-demo"))
    assert await run_step(w.sessionmaker, uuid.UUID(res.json()["job_id"]), "plan", w.gitpilot.deps()) == "failed"
    failed = (await w.signed.get(f"/v1/agent-repairs/{res.json()['job_id']}")).json()
    assert "demo mode" in failed["error"]


async def test_approval_is_enforced_and_may_only_narrow_the_plan(world):
    w = world
    job = await planned(w)
    early = await w.signed.post(f"/v1/agent-repairs/{job}/draft-pr", {"title": "x", "body": "y", "draft": True, "patch_sha256": "x", "verification_run": "r"})
    assert early.status_code == 409
    wider = await w.signed.post(f"/v1/agent-repairs/{job}/approve", {"approved_by": "jordan", "what": "plan", "scope": ["agent.py", "deploy.sh"]})
    assert wider.status_code == 422 and "deploy.sh" in wider.text
    w.gitpilot.plan_files.append({"path": ".env", "action": "MODIFY"})
    job2 = (await w.signed.post("/v1/agent-repairs", create_body(w, "rep-env"))).json()["job_id"]
    await run_step(w.sessionmaker, uuid.UUID(job2), "plan", w.gitpilot.deps())
    forbidden = await w.signed.post(f"/v1/agent-repairs/{job2}/approve", {"approved_by": "jordan", "what": "plan", "scope": [".env"]})
    assert forbidden.status_code == 422 and "forbidden" in forbidden.text
    ok = await w.signed.post(f"/v1/agent-repairs/{job}/approve", {"approved_by": "jordan", "what": "plan", "scope": ["agent.py"]})
    assert ok.json()["state"] == "implementing" and ("agent_repair_step", job, "implement") in w.queue.jobs
    assert "agent_repair.approve" in await audit_actions(w)


async def test_the_patch_is_applied_to_the_pinned_commit_and_checked(world):
    w = world
    job = await planned(w)
    assert await implemented(w, job) == "patch_ready"
    s = (await w.signed.get(f"/v1/agent-repairs/{job}")).json()
    assert s["patch"] == w.repo.patch and s["patch_sha256"].startswith("sha256:") and s["changed_files"] == ["agent.py"]
    assert s["static_checks"]["status"] == "passed" and s["branch"] == "langreplay/rep-1"
    body = next(c[1] for c in w.gitpilot.calls if c[0] == "repair")
    assert body["mode"] == "dry_run" and body["allowed_paths"] == ["agent.py"] and body["human_approval"] is True
    assert "<untrusted-evidence>" in body["issues"][0]["description"] and ".env" in body["forbidden_paths"]
    events = (await w.signed.get(f"/v1/agent-repairs/{job}/events?after=0")).json()
    assert [e["stage"] for e in events["items"]][:2] == ["intake", "plan"] and events["next"] == events["items"][-1]["seq"]
    later = (await w.signed.get(f"/v1/agent-repairs/{job}/events?after={events['next']}")).json()
    assert later == {"items": [], "next": events["next"]}
    assert await audit_actions(w) == ["agent_repair.create", "agent_repair.gitpilot_plan", "agent_repair.approve", "agent_repair.gitpilot_repair"]


async def test_without_static_checks_no_draft_pr_is_opened(world, monkeypatch):
    w = world
    monkeypatch.setenv("SELFREPAIR_AGENT_REPAIR_CHECKS", "[]")
    job = await planned(w)
    assert await implemented(w, job) == "patch_ready"
    s = (await w.signed.get(f"/v1/agent-repairs/{job}")).json()
    assert s["static_checks"]["status"] == "not_configured"
    pr = await w.signed.post(f"/v1/agent-repairs/{job}/draft-pr", {"title": "t", "body": "b", "draft": True, "patch_sha256": s["patch_sha256"], "verification_run": "r"})
    assert pr.status_code == 409 and "SELFREPAIR_AGENT_REPAIR_CHECKS" in pr.text


@pytest.mark.parametrize("problem, message", [
    ("outside", "outside the approved scope"), ("stub", "offline stub"), ("blocked", "answered blocked"),
    ("stale", "does not apply to the pinned base commit"), ("checks", None),
])
async def test_every_way_an_implementation_can_go_wrong_is_reported(world, problem, message):
    w = world
    job = await planned(w)
    if problem == "outside":
        w.gitpilot.patch = w.repo.patch.replace("agent.py", "README.md")
    elif problem == "stub":
        w.gitpilot.stubbed = True
    elif problem == "blocked":
        w.gitpilot.status = "blocked"
    elif problem == "stale":
        w.gitpilot.patch = w.repo.patch.replace("VERSION = 1", "VERSION = 0")
    else:
        w.gitpilot.patch = w.repo.patch.replace("VERSION = 2", "VERSION = 3")      # applies, but the check fails
    state = await implemented(w, job)
    s = (await w.signed.get(f"/v1/agent-repairs/{job}")).json()
    if problem == "checks":
        assert state == "patch_ready" and s["static_checks"]["status"] == "failed" and s["static_checks"]["commands"][0]["exit"] != 0
        pr = await w.signed.post(f"/v1/agent-repairs/{job}/draft-pr", {"title": "t", "body": "b", "draft": True, "patch_sha256": s["patch_sha256"], "verification_run": "r"})
        assert pr.status_code == 409 and "static checks" in pr.text
    else:
        assert state == "failed" and message in s["error"] and s["patch"] is None


async def test_cancellation_wins_over_a_late_result(world):
    w = world
    job = await planned(w)
    await w.signed.post(f"/v1/agent-repairs/{job}/approve", {"approved_by": "jordan", "what": "plan", "scope": ["agent.py"]})
    assert (await w.signed.post(f"/v1/agent-repairs/{job}/cancel", {"reason": "not now"})).json()["state"] == "cancelled"
    assert await run_step(w.sessionmaker, uuid.UUID(job), "implement", w.gitpilot.deps()) == "skipped"
    s = (await w.signed.get(f"/v1/agent-repairs/{job}")).json()
    assert s["state"] == "cancelled" and s["patch"] is None
    assert (await w.signed.post(f"/v1/agent-repairs/{job}/cancel", {})).status_code == 409


async def test_retries_are_approved_and_bounded(world, monkeypatch):
    w = world
    monkeypatch.setenv("SELFREPAIR_AGENT_REPAIR_MAX_RETRIES", "1")
    job = await planned(w)
    await implemented(w, job)
    wrong = await w.signed.post(f"/v1/agent-repairs/{job}/approve", {"approved_by": "kim", "what": "retry", "scope": ["agent.py"], "retry": 5})
    assert wrong.status_code == 409
    ok = await w.signed.post(f"/v1/agent-repairs/{job}/approve", {"approved_by": "kim", "what": "retry", "scope": ["agent.py"], "retry": 1})
    assert ok.json()["state"] == "implementing"
    assert await run_step(w.sessionmaker, uuid.UUID(job), "implement", w.gitpilot.deps()) == "patch_ready"
    over = await w.signed.post(f"/v1/agent-repairs/{job}/approve", {"approved_by": "kim", "what": "retry", "scope": ["agent.py"], "retry": 2})
    assert over.status_code == 409 and "at most 1" in over.text
    tasks = [c[1]["task_id"] for c in w.gitpilot.calls if c[0] == "repair"]
    assert tasks == ["lr-rep-1-0", "lr-rep-1-1"]


async def test_a_draft_pr_pushes_only_the_candidate_branch_and_is_a_draft(world, monkeypatch):
    w = world
    opened = []

    class Opener:
        def __init__(self, token):
            assert token == "gh-token-test"

        def open_draft(self, **kw):
            opened.append(kw)
            return {"url": "https://github.com/acme/agent/pull/12", "number": 12, "draft": True}

    monkeypatch.setattr(routes, "PULL_REQUESTS", Opener)
    job = await planned(w)
    await implemented(w, job)
    s = (await w.signed.get(f"/v1/agent-repairs/{job}")).json()
    wrong = await w.signed.post(f"/v1/agent-repairs/{job}/draft-pr", {"title": "t", "body": "b", "draft": True, "patch_sha256": "sha256:other", "verification_run": "r1"})
    assert wrong.status_code == 409 and "another patch" in wrong.text
    not_draft = await w.signed.post(f"/v1/agent-repairs/{job}/draft-pr", {"title": "t", "body": "b", "draft": False, "patch_sha256": s["patch_sha256"], "verification_run": "r1"})
    assert not_draft.status_code == 422
    res = await w.signed.post(f"/v1/agent-repairs/{job}/draft-pr", {"title": "[LangReplay] fix", "body": "Verified by LangReplay.", "draft": True,
                                                                     "patch_sha256": s["patch_sha256"], "verification_run": "20261113-1", "requested_by": "jordan"})
    assert res.status_code == 200 and res.json() == {"url": "https://github.com/acme/agent/pull/12", "number": 12, "draft": True}
    assert opened[0]["head"] == "langreplay/rep-1" and opened[0]["base"] == "main"
    heads = w.git(w.repo.bare, "for-each-ref", "--format=%(refname)", "refs/heads")
    assert heads.splitlines() == ["refs/heads/langreplay/rep-1", "refs/heads/main"]
    assert w.git(w.repo.bare, "rev-parse", "main") == w.repo.base                          # main untouched
    pushed = w.git(w.repo.bare, "show", "langreplay/rep-1:agent.py")
    assert "VERSION = 2" in pushed
    final = (await w.signed.get(f"/v1/agent-repairs/{job}")).json()
    assert final["state"] == "pr_draft" and final["pr"]["draft"] is True
    assert (await audit_actions(w))[-1] == "agent_repair.draft_pr"


async def test_without_the_worker_queue_the_job_fails_with_the_reason(world):
    w = world
    w.app.state.queue = None
    res = await w.signed.post("/v1/agent-repairs", create_body(w, "rep-noqueue"))
    s = (await w.signed.get(f"/v1/agent-repairs/{res.json()['job_id']}")).json()
    assert s["state"] == "failed" and "worker queue" in s["error"]


async def test_another_org_cannot_see_a_job(world, monkeypatch):
    w = world
    job = (await w.signed.post("/v1/agent-repairs", create_body(w))).json()["job_id"]
    monkeypatch.setenv("SELFREPAIR_AGENT_REPAIR_ORG_ID", str(uuid.uuid4()))
    assert (await w.signed.get(f"/v1/agent-repairs/{job}")).status_code == 404
    assert (await w.signed.get("/v1/agent-repairs/not-a-uuid")).status_code == 404
