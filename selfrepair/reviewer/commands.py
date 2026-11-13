"""Pull-request comment commands.

    @selfrepair review   review the pull request's latest commit again
    @selfrepair fix      ask GitPilot for a draft pull request that addresses
                         the open suggestions of the latest review

The handles come from `reviewer.mentions.handles` (default `selfrepair` and
`gitpilot`). Only commenters whose GitHub `author_association` is listed in
`reviewer.mentions.allowed_associations` are obeyed; anyone else gets no
reaction at all, so a drive-by comment on a public repository cannot spend the
model budget or create branches. Bots are ignored. Quoted lines and code
blocks are not read, so quoting a command does not run it.

A `fix` request counts as the human approval GitPilot's draft-PR mode needs:
the commenter is identified and has write access through their association.
SelfRepair still never approves or merges anything.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Literal

from selfrepair.reviewer.schemas import ReviewEvent

logger = logging.getLogger(__name__)

Command = Literal["review", "fix"]
_VERBS: dict[str, Command] = {"review": "review", "fix": "fix", "address": "fix"}


def parse_command(body: str, handles: list[str]) -> Command | None:
    """Return the first command addressed to one of `handles`, ignoring quotes and code."""
    if not body or not handles:
        return None
    text = re.sub(r"```.*?```", " ", body, flags=re.S)
    text = re.sub(r"`[^`]*`", " ", text)
    names = "|".join(re.escape(h.lstrip("@")) for h in handles if h.strip())
    if not names:
        return None
    pattern = re.compile(rf"(?<![\w/.-])@(?:{names})\b[\s,:]+(\w+)", re.I)
    for line in text.splitlines():
        if line.lstrip().startswith(">"):
            continue
        match = pattern.search(line)
        if match:
            return _VERBS.get(match.group(1).lower())
    return None


def comment_context(payload: dict[str, Any]) -> dict[str, Any] | None:
    """The fields we need from an `issue_comment` delivery on a pull request, or None."""
    if payload.get("action") != "created":
        return None
    issue = payload.get("issue") or {}
    comment = payload.get("comment") or {}
    repo = payload.get("repository") or {}
    if not isinstance(issue, dict) or not issue.get("pull_request"):
        return None
    user = comment.get("user") or {}
    if user.get("type") == "Bot" or str(user.get("login") or "").endswith("[bot]"):
        return None
    try:
        number = int(issue.get("number"))
        comment_id = int(comment.get("id"))
    except (TypeError, ValueError):
        return None
    return {
        "pr_number": number,
        "comment_id": comment_id,
        "body": str(comment.get("body") or ""),
        "login": str(user.get("login") or ""),
        "association": str(comment.get("author_association") or "NONE").upper(),
        "repo_full_name": str(repo.get("full_name") or ""),
        "default_branch": str(repo.get("default_branch") or "main"),
        "installation_id": (payload.get("installation") or {}).get("id"),
    }


def event_from_pull(pr: dict[str, Any], info: dict[str, Any], delivery_id: str) -> ReviewEvent:
    """Build the review event for a `@… review` request from the pull request API object."""
    head = pr.get("head") or {}
    base = pr.get("base") or {}
    head_repo = head.get("repo") or {}
    base_repo = base.get("repo") or {}
    installation = info.get("installation_id")
    return ReviewEvent(
        provider="github",
        kind="pull_request",
        action="comment",
        delivery_id=delivery_id,
        repo_full_name=info["repo_full_name"],
        installation_id=int(installation) if installation else None,
        ref=f"refs/heads/{head.get('ref') or ''}",
        branch=str(head.get("ref") or ""),
        base_branch=str(base.get("ref") or "") or None,
        base_sha=str(base.get("sha") or ""),
        head_sha=str(head.get("sha") or ""),
        pr_number=info["pr_number"],
        from_fork=bool(head_repo) and bool(base_repo)
        and head_repo.get("full_name") != base_repo.get("full_name"),
        sender_login=info["login"],
        sender_type="User",
        default_branch=info["default_branch"],
        title=pr.get("title"),
        # An explicit request reviews drafts too.
        draft=False,
        trigger=f"@{info['login']}",
        trigger_comment_id=info["comment_id"],
    )


async def handle_github_comment(
    ctx: dict[str, Any], delivery_id: str, payload: dict[str, Any]
) -> str | None:
    """Run a comment command. Returns None when the comment is not one of ours,
    so the caller can hand it to Issue Watch instead."""
    from selfrepair.reviewer.dispatcher import _dispatch, store_from_ctx
    from selfrepair.reviewer.settings import resolve_reviewer_config

    info = comment_context(payload)
    if info is None:
        return None
    store = store_from_ctx(ctx)
    if store is None:
        return None
    repo = await store.resolve_repo(
        provider="github", full_name=info["repo_full_name"],
        installation_id=int(info["installation_id"]) if info["installation_id"] else None,
    )
    if repo is None or repo.ambiguous:
        return None
    org_settings, repo_settings = await store.settings_for(org_id=repo.org_id, repo_id=repo.repo_id)
    config = resolve_reviewer_config(
        config_yaml=repo.config_yaml, org_settings=org_settings, repo_settings=repo_settings
    )
    if not config.enabled or not config.mentions.enabled:
        return None
    command = parse_command(info["body"], config.mentions.handles)
    if command is None:
        return None
    if info["association"] not in {a.upper() for a in config.mentions.allowed_associations}:
        logger.info("review command ignored: association=%s", info["association"])
        return "ignored"

    github = ctx.get("github_client") or await _github_client(ctx, info, repo)
    if github is None:
        return "unpublished"
    if command == "review":
        pr = await github.get_pull(info["repo_full_name"], info["pr_number"])
        if not pr:
            return "ignored"
        # Keyed on the comment, so a redelivered webhook is the same request.
        event = event_from_pull(pr, info, f"review-comment:{info['comment_id']}")
        return await _dispatch(ctx, event)
    return await _fix(ctx, store, config, github, info)


async def _fix(ctx: dict[str, Any], store: Any, config: Any, github: Any, info: dict[str, Any]) -> str:
    """Send the open suggestions of this pull request's latest review to GitPilot."""
    from selfrepair.reviewer.remediation import (
        RemediationRefused,
        create_task,
        execute_task,
        gitpilot_client_from_env,
    )

    repo_name, number = info["repo_full_name"], info["pr_number"]
    # One fix per comment. GitHub redelivers webhooks and each `create_task`
    # gets a new task id, so without this claim a redelivery would ask GitPilot
    # for a second branch and draft pull request.
    if not await store.claim_delivery(provider="github", delivery_id=f"fix-comment:{info['comment_id']}"):
        return "duplicate"
    await github.react(repo_name, info["comment_id"], "eyes")
    run = await _latest_run(store, info)
    if run is None:
        await github.comment(repo_name, number, "There is no review of this pull request to fix yet. "
                             "Comment `@selfrepair review` first.")
        return "ignored"
    findings = [f for f in await store.list_findings(run.id)
                if f.validation_state == "accepted" and f.resolution_state == "open"]
    if not findings:
        await github.comment(repo_name, number, "The latest review has no open suggestions to fix. 🎉")
        return "ignored"
    try:
        task = await create_task(
            store=store, run=run, config=config,
            fingerprints=[f.fingerprint for f in findings][:50],
            allowed_paths=None, approve=True, requested_by=info["login"],
        )
    except RemediationRefused as exc:
        await github.comment(repo_name, number, f"I can't hand this to GitPilot: {exc.reason}.")
        return "refused"
    await github.comment(
        repo_name, number,
        f"🛠️ Asked GitPilot to address {len(findings)} suggestion(s) from the review of "
        f"`{run.head_sha[:10]}` (requested by @{info['login']}). "
        f"GitPilot works on branch `gitpilot/{task['id']}` and opens a **draft** pull request; "
        "a person reviews and merges it.",
    )
    queue = ctx.get("redis") or ctx.get("queue")
    if queue is not None and hasattr(queue, "enqueue_job"):
        await queue.enqueue_job("remediate_review", str(run.id), task["id"])
        return "queued"
    done = await execute_task(store=store, review_id=run.id, task_id=task["id"],
                              client=ctx.get("gitpilot_client") or gitpilot_client_from_env())
    result = done.get("result") or {}
    if result.get("pr_url"):
        await github.comment(repo_name, number, f"GitPilot opened a draft pull request: {result['pr_url']}")
    elif done.get("status") != "completed":
        reason = done.get("error") or done.get("status")
        await github.comment(repo_name, number, f"GitPilot did not produce a pull request ({reason}).")
    return str(done.get("status"))


async def _latest_run(store: Any, info: dict[str, Any]) -> Any:
    repo = await store.resolve_repo(
        provider="github", full_name=info["repo_full_name"],
        installation_id=int(info["installation_id"]) if info["installation_id"] else None,
    )
    runs = await store.list_runs(org_id=repo.org_id, repo_id=repo.repo_id, limit=100)
    candidates = [r for r in runs if r.pr_number == info["pr_number"] and r.status != "superseded"]
    candidates.sort(key=lambda r: r.started_at or r.completed_at or 0, reverse=True)
    return candidates[0] if candidates else None


class GitHubCommands:
    """The few GitHub calls the commands need, with an installation token."""

    def __init__(self, transport: Any, token: str, api_url: str = "https://api.github.com") -> None:
        self._t = transport
        self._token = token
        self._api = api_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def get_pull(self, repo: str, number: int) -> dict[str, Any] | None:
        response = await self._t.get(f"{self._api}/repos/{repo}/pulls/{number}", self._headers())
        if getattr(response, "status_code", 0) >= 400:
            return None
        data = response.json()
        return data if isinstance(data, dict) else None

    async def comment(self, repo: str, number: int, body: str) -> None:
        await self._t.post(f"{self._api}/repos/{repo}/issues/{number}/comments",
                           json={"body": body}, headers=self._headers())

    async def react(self, repo: str, comment_id: int, content: str) -> None:
        await self._t.post(f"{self._api}/repos/{repo}/issues/comments/{comment_id}/reactions",
                           json={"content": content}, headers=self._headers())


async def _github_client(ctx: dict[str, Any], info: dict[str, Any], repo: Any) -> GitHubCommands | None:
    from selfrepair.reviewer.credentials import github_token_for
    from selfrepair.reviewer.publishers import HttpxTransport

    installation = info["installation_id"] or repo.installation_id
    token = await github_token_for(int(installation) if installation else None, app=ctx.get("github_app"))
    if not token:
        logger.info("review command has no github credentials repo=%s", info["repo_full_name"])
        return None
    return GitHubCommands(HttpxTransport(), token)
