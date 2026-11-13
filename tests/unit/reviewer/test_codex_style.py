"""Codex-style review: presentation, the model engine, and comment commands."""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from selfrepair.config.repo_config import ReviewerConfig
from selfrepair.reviewer import presentation
from selfrepair.reviewer.commands import handle_github_comment, parse_command
from selfrepair.reviewer.diff import parse_unified_diff
from selfrepair.reviewer.engines.llm_engine import (
    LLMReviewEngine,
    parse_response,
    render_file,
)
from selfrepair.reviewer.presentation import PublishOptions
from selfrepair.reviewer.publishers import GitHubHttpPublisher, build_payloads
from selfrepair.reviewer.schemas import (
    DiffSet,
    EngineUnavailable,
    FindingRecord,
    ReviewEvent,
    RunRecord,
)
from selfrepair.reviewer.service import StaticDiffProvider
from tests.unit.reviewer.conftest import ORG, REPO, store_with_repo

FORM_DIFF = """diff --git a/web/Hub.jsx b/web/Hub.jsx
--- a/web/Hub.jsx
+++ b/web/Hub.jsx
@@ -10,3 +10,5 @@ export default function Hub() {
   return (
+    <form onSubmit={submit}>
+      <div className="connector-dialog-body">{body}</div>
     </div>
"""


def _event(**kw: Any) -> ReviewEvent:
    data = dict(provider="github", kind="pull_request", action="opened", delivery_id="d1",
                repo_full_name="octo/demo", branch="feat", base_branch="main",
                base_sha="a" * 40, head_sha="af3a4d70d7" + "0" * 30, pr_number=7,
                trigger="PR opened", installation_id=99)
    data.update(kw)
    return ReviewEvent(**data)


def _run() -> RunRecord:
    return RunRecord(id=uuid.uuid4(), org_id=ORG, repo_id=REPO, provider="github",
                     event_type="pull_request", base_sha="a" * 40,
                     head_sha="af3a4d70d7" + "0" * 30, engine="llm", policy_version="1",
                     status="running", pr_number=7)


def _finding(severity: str = "medium", fp: str = "f1", line: int = 11) -> FindingRecord:
    return FindingRecord(category="correctness", severity=severity, file_path="web/Hub.jsx",
                         start_line=line, title="Allow the configuration form to shrink and scroll",
                         description="On short viewports the form clips the submit button.",
                         fingerprint=fp, source="llm")


# ── presentation ─────────────────────────────────────────────────────────────

def test_inline_comment_matches_the_codex_layout() -> None:
    body = presentation.inline_comment(_finding("medium"))
    assert body.startswith(
        "**<sub><sub>![P2 Badge](https://img.shields.io/badge/P2-yellow?style=flat)</sub></sub>"
        "  Allow the configuration form to shrink and scroll**"
    )
    assert "Useful? React with 👍 / 👎." in body
    assert body.rstrip().endswith("<!-- sr-finding:f1 -->")


def test_priorities_follow_severity() -> None:
    assert [presentation.priority(s) for s in ("critical", "high", "medium", "low", "info")] == [
        "P0", "P1", "P2", "P3", "P3"]


def test_review_body_names_the_reviewed_commit() -> None:
    body = presentation.review_body("af3a4d70d7ffff", [_finding()], posted_inline=1)
    assert body.startswith("### 💡 SelfRepair Review")
    assert "Here are some automated review suggestions for this pull request." in body
    assert "Reviewed commit: `af3a4d70d7`" in body


def test_clean_review_says_so() -> None:
    assert "Didn't find any major issues" in presentation.review_body("abc", [], posted_inline=0)


def test_summary_comment_round_trips_and_escapes() -> None:
    row = presentation.summary_row(status="completed", head_sha="af3a4d70d7", trigger="@eve | <b>x</b>")
    body = presentation.summary_comment([row])
    assert "<summary><strong>SelfRepair Review Summary</strong>: ✅ Completed</summary>" in body
    assert "| 📝 **Code Review** | ✅ **Completed** <relative-time datetime=" in body
    assert "`af3a4d7`" in body
    assert "<b>" not in body.split(presentation.SUMMARY_MARKER)[0]
    assert "\\|" in body
    rows = presentation.rows_from_comment(body)
    assert rows[0]["commit"] == "af3a4d7"
    newer = presentation.merge_row(rows, presentation.summary_row(status="in_progress", head_sha="b" * 40, trigger="New commits"))
    assert [r["status"] for r in newer] == ["in_progress", "completed"]


def test_rows_from_a_tampered_comment_are_sanitised() -> None:
    body = presentation.SUMMARY_MARKER + ' {"rows": [{"status": "evil", "commit": "zz<script>", "trigger": "x|y"}]} -->'
    row = presentation.rows_from_comment(body)[0]
    assert row["status"] == "completed" and "<" not in row["commit"] and row["trigger"] == "x\\|y"


# ── payloads ─────────────────────────────────────────────────────────────────

def test_codex_payload_inlines_p2_and_lists_p3() -> None:
    findings = [_finding("medium", "f1"), _finding("low", "f2", line=12)]
    payloads = build_payloads(event=_event(), run=_run(), findings=findings, conclusion="success",
                              summary="s", already_published=set(), options=PublishOptions())
    review = next(p for p in payloads if p["kind"] == "review")["body"]
    assert review["event"] == "COMMENT"
    assert [c["line"] for c in review["comments"]] == [11]
    assert "outside the inline threshold" in review["body"]


def test_codex_skips_a_review_when_everything_was_already_posted() -> None:
    payloads = build_payloads(event=_event(), run=_run(), findings=[_finding()], conclusion="success",
                              summary="s", already_published={"f1"}, options=PublishOptions())
    assert [p["kind"] for p in payloads] == ["check"]


def test_classic_style_is_unchanged_without_options() -> None:
    payloads = build_payloads(event=_event(), run=_run(), findings=[_finding()], conclusion="success",
                              summary="s", already_published=set())
    review = next(p for p in payloads if p["kind"] == "review")["body"]
    assert review["comments"][0]["body"].startswith("**medium**")


# ── GitHub publisher: status comment and reactions ───────────────────────────

class FakeTransport:
    def __init__(self, comments: list[dict[str, Any]] | None = None) -> None:
        self.calls: list[tuple[str, str, Any]] = []
        self.comments = comments or []

    async def get(self, url: str, headers: dict[str, str]) -> Any:
        self.calls.append(("GET", url, None))
        return SimpleNamespace(status_code=200, json=lambda: self.comments, headers={})

    async def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> Any:
        self.calls.append(("POST", url, json))
        return SimpleNamespace(status_code=201, json=lambda: {"id": 5}, headers={}, text="")

    async def patch(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> Any:
        self.calls.append(("PATCH", url, json))
        return SimpleNamespace(status_code=200, json=lambda: {"id": 5}, headers={}, text="")


async def test_announce_reacts_and_creates_the_status_comment() -> None:
    transport = FakeTransport()
    pub = GitHubHttpPublisher(transport, token="t")
    await pub.announce(event=_event(trigger_comment_id=42), run=_run(), options=PublishOptions())
    urls = [(m, u) for m, u, _ in transport.calls]
    assert ("POST", "https://api.github.com/repos/octo/demo/issues/comments/42/reactions") in urls
    created = [b for m, u, b in transport.calls if m == "POST" and u.endswith("/issues/7/comments")]
    assert "🔄 **Running** since <relative-time" in created[0]["body"]


async def test_publish_edits_only_the_bots_status_comment() -> None:
    old = presentation.summary_comment([presentation.summary_row(status="in_progress", head_sha="af3a4d70d7", trigger="PR opened")])
    comments = [
        {"id": 1, "user": {"type": "User"}, "body": old},          # a person quoting it
        {"id": 2, "user": {"type": "Bot"}, "body": old},
    ]
    transport = FakeTransport(comments)
    pub = GitHubHttpPublisher(transport, token="t")
    await pub.publish(event=_event(), run=_run(), findings=[], conclusion="success", summary="s",
                      already_published=set(), options=PublishOptions())
    patches = [(u, b) for m, u, b in transport.calls if m == "PATCH"]
    assert patches[0][0].endswith("/issues/comments/2")
    edited = patches[0][1]["body"]
    assert "<strong>SelfRepair Review Summary</strong>: ✅ Completed" in edited
    assert "Running" not in edited.split("<details> <summary>ℹ️")[0]
    assert any(u.endswith("/issues/7/reactions") and b == {"content": "+1"} for m, u, b in transport.calls)


# ── model engine ─────────────────────────────────────────────────────────────

def _diff(text: str = FORM_DIFF) -> DiffSet:
    return DiffSet(files=parse_unified_diff(text), source="test")


def test_render_numbers_new_lines() -> None:
    rendered = render_file(_diff().files[0])
    assert "   11 +    <form onSubmit={submit}>" in rendered
    assert "   12 +      <div" in rendered


def test_parse_response_accepts_fenced_json() -> None:
    assert parse_response('```json\n{"findings": []}\n```') == {"findings": []}
    with pytest.raises(EngineUnavailable):
        parse_response("I think it is fine")


def _llm(reply: dict[str, Any] | None = None, status: int = 200, seen: list | None = None) -> LLMReviewEngine:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(json.loads(request.content))
        if status != 200:
            return httpx.Response(status, json={"error": "no"})
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(reply)}}]})
    return LLMReviewEngine(url="https://llm.test/v1", model="code-review", api_key="k",
                           transport=httpx.MockTransport(handler))


def test_llm_engine_keeps_confident_findings_on_diff_files() -> None:
    reply = {"summary": "One layout bug.", "findings": [
        {"title": "Allow the configuration form to shrink and scroll", "body": "Clips on phones.",
         "priority": "P2", "category": "correctness", "confidence": 0.9, "file": "web/Hub.jsx", "line": 11},
        {"title": "Guess", "body": "Maybe.", "priority": "P1", "confidence": 0.2, "file": "web/Hub.jsx", "line": 12},
        {"title": "Other file", "body": "x", "priority": "P0", "confidence": 0.9, "file": "nope.py", "line": 1},
    ]}
    report = _llm(reply).review(_event(), _diff(), ReviewerConfig(enabled=True, engine="llm"))
    assert report.engine == "llm" and report.model_id == "code-review"
    assert [(f.severity, f.start_line, f.source) for f in report.findings] == [("medium", 11, "llm")]


def test_llm_engine_redacts_secrets_before_sending() -> None:
    seen: list = []
    secret_diff = FORM_DIFF.replace("{body}", "{'ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8'}")
    _llm({"findings": []}, seen=seen).review(_event(), _diff(secret_diff), ReviewerConfig(enabled=True))
    assert "ghp_A1b2" not in json.dumps(seen)


def test_llm_engine_without_config_or_with_a_refused_key_is_unavailable(monkeypatch) -> None:
    for name in ("SELFREPAIR_REVIEW_LLM_URL", "SELFREPAIR_OLLABRIDGE_URL", "OLLABRIDGE_BASE_URL", "OPENAI_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(EngineUnavailable):
        LLMReviewEngine(model="m").review(_event(), _diff(), ReviewerConfig())
    with pytest.raises(EngineUnavailable, match="refused"):
        _llm(status=401).review(_event(), _diff(), ReviewerConfig())


# ── comment commands ─────────────────────────────────────────────────────────

@pytest.mark.parametrize(("body", "expected"), [
    ("@selfrepair review", "review"),
    ("Thanks! @SelfRepair review please", "review"),
    ("@gitpilot fix", "fix"),
    ("@selfrepair address that feedback", "fix"),
    ("> @selfrepair review", None),
    ("`@selfrepair review`", None),
    ("```\n@selfrepair review\n```", None),
    ("email me at me@selfrepair review", None),
    ("@codex review", None),
])
def test_parse_command(body: str, expected: str | None) -> None:
    assert parse_command(body, ["selfrepair", "gitpilot"]) == expected


def _comment(body: str, association: str = "OWNER", user_type: str = "User") -> dict[str, Any]:
    return {
        "action": "created",
        "issue": {"number": 7, "pull_request": {"url": "x"}},
        "comment": {"id": 42, "body": body, "author_association": association,
                    "user": {"login": "ruslanmv", "type": user_type}},
        "repository": {"full_name": "octo/demo", "default_branch": "main"},
        "installation": {"id": 99},
    }


class FakeGitHub:
    def __init__(self) -> None:
        self.comments: list[str] = []
        self.reactions: list[tuple[int, str]] = []

    async def get_pull(self, repo: str, number: int) -> dict[str, Any]:
        return {"title": "Pairing", "head": {"sha": "b" * 40, "ref": "feat", "repo": {"full_name": repo}},
                "base": {"sha": "a" * 40, "ref": "main", "repo": {"full_name": repo}}}

    async def comment(self, repo: str, number: int, body: str) -> None:
        self.comments.append(body)

    async def react(self, repo: str, comment_id: int, content: str) -> None:
        self.reactions.append((comment_id, content))


def _ctx(store: Any, github: FakeGitHub, **extra: Any) -> dict[str, Any]:
    from tests.unit.reviewer.conftest import VULN_DIFF
    return {"review_store": store, "diff_provider": StaticDiffProvider(parse_unified_diff(VULN_DIFF)),
            "github_client": github, "job_try": 1, **extra}


async def test_review_command_reviews_the_latest_commit_with_the_comment_as_trigger() -> None:
    store = store_with_repo()
    github = FakeGitHub()
    outcome = await handle_github_comment(_ctx(store, github), "c1", _comment("@selfrepair review"))
    assert outcome == "reviewed"
    runs = await store.list_runs(org_id=ORG, repo_id=REPO)
    assert runs[0].head_sha == "b" * 40 and runs[0].pr_number == 7


async def test_commands_from_outsiders_and_bots_are_ignored() -> None:
    store = store_with_repo()
    github = FakeGitHub()
    assert await handle_github_comment(_ctx(store, github), "c1", _comment("@selfrepair review", "NONE")) == "ignored"
    assert await handle_github_comment(_ctx(store, github), "c2", _comment("@selfrepair review", user_type="Bot")) is None
    assert await handle_github_comment(_ctx(store, github), "c3", _comment("nice work")) is None
    assert await store.list_runs(org_id=ORG, repo_id=REPO) == []


async def test_fix_command_sends_a_human_approved_draft_task_to_gitpilot() -> None:
    yaml = "version: 1\nreviewer:\n  enabled: true\n  remediation:\n    enabled: true\n"
    store = store_with_repo(config_yaml=yaml)
    github = FakeGitHub()
    sent: list[dict[str, Any]] = []

    class GitPilot:
        def repair(self, plan: dict[str, Any], *, dry_run: bool = True) -> dict[str, Any]:
            assert dry_run is False
            sent.append(plan)
            return {"status": "ok", "pr_url": "https://github.com/octo/demo/pull/8"}

    ctx = _ctx(store, github, gitpilot_client=GitPilot())
    await handle_github_comment(ctx, "c1", _comment("@selfrepair review"))
    outcome = await handle_github_comment(ctx, "c2", _comment("@selfrepair fix"))
    assert outcome == "completed"
    assert sent[0]["mode"] == "draft_pr" and sent[0]["auto_merge"] is False
    assert any("pull/8" in c for c in github.comments)
    assert (42, "eyes") in github.reactions


async def test_fix_command_is_refused_when_remediation_is_off() -> None:
    store = store_with_repo()
    github = FakeGitHub()
    ctx = _ctx(store, github)
    await handle_github_comment(ctx, "c1", _comment("@selfrepair review"))
    assert await handle_github_comment(ctx, "c2", _comment("@selfrepair fix")) == "refused"
    assert "remediation disabled" in github.comments[-1]


# ── regressions for review findings on ruslanmv/SelfRepair#13 ───────────────

def _big_diff(lines: int, width: int = 40) -> str:
    body = "".join(f"+line {i:05d} " + "x" * width + "\n" for i in range(lines))
    return f"diff --git a/big.py b/big.py\n--- a/big.py\n+++ b/big.py\n@@ -0,0 +1,{lines} @@\n{body}"


def test_oversized_files_are_split_not_truncated(monkeypatch) -> None:
    from selfrepair.reviewer.engines import llm_engine

    monkeypatch.setattr(llm_engine, "_CHUNK_CHARS", 2_000)
    seen: list = []
    report = _llm({"findings": []}, seen=seen).review(_event(), _diff(_big_diff(120)), ReviewerConfig())
    sent = "".join(m["messages"][1]["content"] for m in seen)
    assert len(seen) > 1
    assert all(f"line {i:05d}" in sent for i in range(120))
    assert report.incomplete_reason is None


def test_too_many_parts_or_cut_lines_make_the_review_incomplete(monkeypatch) -> None:
    from selfrepair.reviewer.engines import llm_engine

    monkeypatch.setattr(llm_engine, "_CHUNK_CHARS", 2_000)
    report = _llm({"findings": []}).review(_event(), _diff(_big_diff(1_200)), ReviewerConfig())
    assert report.incomplete_reason and "diff too large" in report.incomplete_reason
    report = _llm({"findings": []}).review(_event(), _diff(_big_diff(3, width=5_000)), ReviewerConfig())
    assert report.incomplete_reason and "too long" in report.incomplete_reason


@pytest.mark.parametrize("reply", [{}, {"error": "request refused"}, {"findings": "invalid"}, {"findings": ["x"]}])
def test_replies_without_a_findings_list_are_not_a_review(reply) -> None:
    with pytest.raises(EngineUnavailable):
        _llm(reply).review(_event(), _diff(), ReviewerConfig())


def test_incomplete_review_never_claims_a_clean_result() -> None:
    payloads = build_payloads(event=_event(), run=_run(), findings=[], conclusion="action_required",
                              summary="Engine: llm\nIncomplete: model endpoint refused the key (401)",
                              already_published=set(), options=PublishOptions())
    body = next(p for p in payloads if p["kind"] == "review")["body"]["body"]
    assert "Didn't find any major issues" not in body
    assert "Couldn't finish reviewing this commit" in body and "refused the key" in body


async def test_incomplete_review_gets_no_thumbs_up() -> None:
    transport = FakeTransport()
    await GitHubHttpPublisher(transport, token="t").publish(
        event=_event(), run=_run(), findings=[], conclusion="action_required",
        summary="Incomplete: x", already_published=set(), options=PublishOptions())
    assert not any(u.endswith("/reactions") and b == {"content": "+1"} for m, u, b in transport.calls)


async def test_a_redelivered_fix_comment_does_not_start_a_second_task() -> None:
    yaml = "version: 1\nreviewer:\n  enabled: true\n  remediation:\n    enabled: true\n"
    store = store_with_repo(config_yaml=yaml)
    github = FakeGitHub()
    calls: list = []

    class GitPilot:
        def repair(self, plan, *, dry_run=True):
            calls.append(plan)
            return {"status": "ok"}

    ctx = _ctx(store, github, gitpilot_client=GitPilot())
    await handle_github_comment(ctx, "c1", _comment("@selfrepair review"))
    fix = _comment("@selfrepair fix")
    fix["comment"]["id"] = 43
    assert await handle_github_comment(ctx, "d-a", fix) == "completed"
    assert await handle_github_comment(ctx, "d-b", fix) == "duplicate"
    assert len(calls) == 1


# ── regressions from reviewing ruslanmv/SelfRepair#14 (67 files, 3.4M chars) ──

def test_generated_files_are_skipped_not_truncating_the_review() -> None:
    from selfrepair.reviewer.diff import is_generated, limit_diff

    bundle = parse_unified_diff(_big_diff(10).replace("big.py", "spa/assets/index-Dx2aEjyp.js"))
    source = parse_unified_diff(FORM_DIFF)
    limited = limit_diff(bundle + source)
    assert limited.changed_paths() == ["web/Hub.jsx"]
    assert limited.skipped == ["spa/assets/index-Dx2aEjyp.js"] and not limited.truncated
    assert is_generated("package-lock.json") and is_generated("app.js.map")
    assert not is_generated("docs/build/guide.md") and not is_generated("src/assets/logo.svg")


def test_code_redaction_keeps_code_and_hides_values() -> None:
    from selfrepair.ci.redaction import redact_code

    code = 'secret = os.environ.get("KEY")\ntoken = payload.get("device_token")\npassword = "hunter2hunter2"'
    out = redact_code(code).text
    assert 'secret = os.environ.get("KEY")' in out and 'token = payload.get("device_token")' in out
    assert "hunter2hunter2" not in out and 'password = "<<REDACTED:kv_secret:' in out


def test_a_file_that_mentions_the_cut_marker_is_not_cut() -> None:
    text = 'diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n@@ -0,0 +1 @@\n+_CUT = " …[line cut]"\n'
    report = _llm({"findings": []}).review(_event(), _diff(text), ReviewerConfig())
    assert report.incomplete_reason is None


def _scripted(replies: list[Any], seen: list | None = None) -> LLMReviewEngine:
    queue = list(replies)

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(json.loads(request.content))
        reply = queue.pop(0) if queue else {"findings": []}
        if isinstance(reply, int):
            return httpx.Response(reply, json={})
        content = reply if isinstance(reply, str) else json.dumps(reply)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    return LLMReviewEngine(url="https://llm.test/v1", model="m", api_key="k",
                           transport=httpx.MockTransport(handler))


GOOD = {"title": "Allow the form to shrink", "body": "Clips on phones.", "priority": "P2",
        "confidence": 0.9, "file": "web/Hub.jsx", "line": 11}


def test_a_cut_off_reply_is_retried_once() -> None:
    seen: list = []
    report = _scripted(['```json\n{"findings": [{"title": "Allow', {"findings": [GOOD]}], seen).review(
        _event(), _diff(), ReviewerConfig())
    assert len(seen) == 2 and "compact JSON" in seen[1]["messages"][1]["content"]
    assert [f.start_line for f in report.findings] == [11] and report.incomplete_reason is None


def test_complete_findings_are_salvaged_from_a_cut_off_retry() -> None:
    cut = '{"findings": [' + json.dumps(GOOD) + ', {"title": "Second", "bo'
    report = _scripted([cut, cut]).review(_event(), _diff(), ReviewerConfig())
    assert [f.start_line for f in report.findings] == [11]
    assert report.incomplete_reason and "kept 1 complete finding" in report.incomplete_reason


def test_one_bad_part_does_not_discard_the_others(monkeypatch) -> None:
    from selfrepair.reviewer.engines import llm_engine

    monkeypatch.setattr(llm_engine, "_CHUNK_CHARS", 300)
    monkeypatch.setattr(llm_engine, "_PARALLEL", 1)
    two_files = FORM_DIFF + FORM_DIFF.replace("web/Hub.jsx", "web/Other.jsx")
    report = _scripted(["nope", "still nope", {"findings": [dict(GOOD, file="web/Other.jsx")]}]).review(
        _event(), _diff(two_files), ReviewerConfig())
    assert [f.file_path for f in report.findings] == ["web/Other.jsx"]
    assert report.incomplete_reason and report.incomplete_reason.startswith("1 of 2 parts")


def test_a_refused_key_stops_the_whole_review() -> None:
    with pytest.raises(EngineUnavailable, match="refused"):
        _scripted([401]).review(_event(), _diff(), ReviewerConfig())


def test_duplicate_findings_on_one_line_keep_the_most_severe() -> None:
    from selfrepair.reviewer.engines.llm_engine import dedupe_findings

    low = _finding("low", "a")
    high = _finding("high", "b")
    assert [f.severity for f in dedupe_findings([low, high])] == ["high"]


def test_inline_comments_are_capped_by_priority() -> None:
    findings = [_finding("medium", f"m{i}", line=11) for i in range(3)] + [_finding("critical", "c", line=12)]
    payloads = build_payloads(event=_event(), run=_run(), findings=findings, conclusion="failure", summary="s",
                              already_published=set(), options=PublishOptions(max_inline_comments=2))
    review = next(p for p in payloads if p["kind"] == "review")["body"]
    assert [c["line"] for c in review["comments"]] == [12, 11]
    assert "outside the inline threshold" in review["body"]


def test_security_code_is_reviewed_first() -> None:
    from selfrepair.reviewer.engines.llm_engine import review_priority
    from selfrepair.reviewer.schemas import DiffFile

    paths = ["README.md", "tests/test_x.py", ".github/workflows/ci.yml", "app/views.py", "app/auth.py"]
    ordered = sorted((DiffFile(path=p, patch="x") for p in paths), key=review_priority)
    assert [f.path for f in ordered] == ["app/auth.py", "app/views.py", ".github/workflows/ci.yml",
                                         "tests/test_x.py", "README.md"]
