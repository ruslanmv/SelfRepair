"""Normalize GitHub and GitLab webhook payloads into `ReviewEvent`."""
from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from selfrepair.reviewer.schemas import ZERO_SHA, CommitInfo, ReviewEvent

_PR_ACTIONS = frozenset(
    {"opened", "reopened", "synchronize", "ready_for_review", "edited"}
)
_PR_TRIGGERS = {
    "opened": "PR opened",
    "reopened": "PR reopened",
    "synchronize": "New commits",
    "ready_for_review": "Ready for review",
    "edited": "PR edited",
}
_BOT_LOGINS = frozenset({"selfrepair", "selfrepair[bot]"})


class EventRejected(Exception):
    """The payload is not a reviewable event. `reason` is a stable code."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def event_from_run(run: Any, repo: Any) -> ReviewEvent:
    """Rebuild a review event from a stored run so a retry uses the same SHAs."""
    meta = dict(run.metadata or {})
    kind = run.event_type if run.event_type in {"push", "pull_request", "merge_request"} else "push"
    provider = run.provider if run.provider in {"github", "gitlab"} else "github"
    ref = run.ref or f"refs/heads/{meta.get('branch') or repo.default_branch}"
    branch = str(meta.get("branch") or ref.rsplit("/", 1)[-1])
    project_id = meta.get("project_id")
    installation = meta.get("installation_id")
    if installation is None:
        installation = repo.installation_id
    return ReviewEvent(
        provider=provider,
        kind=kind,
        action="retry",
        trigger="Retry",
        delivery_id=run.delivery_id or f"retry-{run.id}",
        repo_full_name=repo.full_name,
        installation_id=int(installation) if isinstance(installation, int) else None,
        project_id=int(project_id) if isinstance(project_id, int) else None,
        ref=ref,
        branch=branch,
        base_branch=meta.get("base_branch"),
        base_sha=run.base_sha,
        head_sha=run.head_sha,
        forced=run.forced,
        pr_number=run.pr_number,
        from_fork=run.from_fork,
        sender_login=run.sender_login,
        default_branch=repo.default_branch,
        commits=[CommitInfo(sha=sha) for sha in run.commit_shas],
    )


def github_event(event_type: str, delivery_id: str, payload: dict[str, Any]) -> ReviewEvent:
    """Parse a GitHub `push` or `pull_request` payload."""
    repo = payload.get("repository") or {}
    full_name = repo.get("full_name")
    if not isinstance(full_name, str) or not full_name:
        raise EventRejected("malformed")
    installation = payload.get("installation") or {}
    installation_id = installation.get("id")
    sender = payload.get("sender") or {}
    if event_type == "push":
        return _github_push(delivery_id, payload, full_name, installation_id, sender, repo)
    if event_type == "pull_request":
        return _github_pull(delivery_id, payload, full_name, installation_id, sender, repo)
    raise EventRejected("unsupported_event")


def gitlab_merge_request(delivery_id: str, payload: dict[str, Any]) -> ReviewEvent:
    """Parse a GitLab Merge Request Hook payload."""
    project = payload.get("project") or {}
    attrs = payload.get("object_attributes") or {}
    full_name = project.get("path_with_namespace")
    if not isinstance(full_name, str) or not attrs:
        raise EventRejected("malformed")
    action = str(attrs.get("action") or "")
    if action in {"close", "merge", "approved", "unapproved"}:
        raise EventRejected("ignored_action")
    if action not in {"open", "reopen", "update"}:
        raise EventRejected("ignored_action")
    user = payload.get("user") or {}
    last = attrs.get("last_commit") or {}
    head = str(last.get("id") or attrs.get("last_commit_id") or "")
    base = str(attrs.get("oldrev") or "") or ZERO_SHA
    if action == "open":
        base = ZERO_SHA
    if not head or head == ZERO_SHA:
        raise EventRejected("malformed")
    source = attrs.get("source") or {}
    target = attrs.get("target") or {}
    from_fork = bool(source) and bool(target) and source.get("id") != target.get("id")
    return ReviewEvent(
        provider="gitlab",
        kind="merge_request",
        action=action,
        delivery_id=delivery_id,
        repo_full_name=full_name,
        project_id=project.get("id") or attrs.get("target_project_id"),
        ref=f"refs/heads/{attrs.get('source_branch') or ''}",
        branch=str(attrs.get("source_branch") or ""),
        base_branch=str(attrs.get("target_branch") or "") or None,
        base_sha=base,
        head_sha=head,
        pr_number=int(attrs.get("iid") or 0) or None,
        from_fork=from_fork,
        sender_login=user.get("username"),
        default_branch=str(project.get("default_branch") or "main"),
        title=attrs.get("title"),
        draft=bool(attrs.get("draft") or attrs.get("work_in_progress")),
    )


def recursion_risk(event: ReviewEvent) -> bool:
    """True when reviewing this event could review SelfRepair's own repair push."""
    branch = event.branch or ""
    if branch.startswith("selfrepair/"):
        return True
    login = (event.sender_login or "").lower()
    if login in _BOT_LOGINS:
        return True
    for commit in event.commits:
        if "SelfRepair-Review: ignore" in commit.message:
            return True
    return False


def _github_push(
    delivery_id: str,
    payload: dict[str, Any],
    full_name: str,
    installation_id: Any,
    sender: dict[str, Any],
    repo: dict[str, Any],
) -> ReviewEvent:
    ref = payload.get("ref") or ""
    if not isinstance(ref, str) or not ref.startswith("refs/heads/"):
        raise EventRejected("not_a_branch")
    before = str(payload.get("before") or ZERO_SHA)
    after = str(payload.get("after") or ZERO_SHA)
    deleted = after == ZERO_SHA
    commits = []
    for item in payload.get("commits") or []:
        if isinstance(item, dict) and item.get("id"):
            commits.append(
                CommitInfo(sha=str(item["id"]), message=str(item.get("message") or ""))
            )
    try:
        return ReviewEvent(
            provider="github",
            kind="push",
            delivery_id=delivery_id,
            repo_full_name=full_name,
            installation_id=int(installation_id) if installation_id else None,
            ref=ref,
            branch=ref.removeprefix("refs/heads/"),
            base_sha=before,
            head_sha=after,
            forced=bool(payload.get("forced")),
            deleted=deleted,
            commits=commits,
            sender_login=(sender.get("login") if isinstance(sender, dict) else None),
            sender_type=(sender.get("type") if isinstance(sender, dict) else None),
            default_branch=str(repo.get("default_branch") or "main"),
            compare_url=payload.get("compare"),
        )
    except ValidationError as exc:
        raise EventRejected("malformed") from exc


def _github_pull(
    delivery_id: str,
    payload: dict[str, Any],
    full_name: str,
    installation_id: Any,
    sender: dict[str, Any],
    repo: dict[str, Any],
) -> ReviewEvent:
    action = str(payload.get("action") or "")
    if action not in _PR_ACTIONS:
        raise EventRejected("ignored_action")
    pr = payload.get("pull_request") or {}
    if not isinstance(pr, dict):
        raise EventRejected("malformed")
    head = pr.get("head") or {}
    base = pr.get("base") or {}
    head_sha = str(head.get("sha") or "")
    base_sha = str(base.get("sha") or "")
    if not head_sha or not base_sha:
        raise EventRejected("malformed")
    head_repo = head.get("repo") or {}
    base_repo = base.get("repo") or {}
    from_fork = bool(head_repo) and bool(base_repo) and head_repo.get("full_name") != base_repo.get(
        "full_name"
    )
    try:
        return ReviewEvent(
            provider="github",
            kind="pull_request",
            action=action,
            delivery_id=delivery_id,
            repo_full_name=full_name,
            installation_id=int(installation_id) if installation_id else None,
            ref=f"refs/heads/{head.get('ref') or ''}",
            branch=str(head.get("ref") or ""),
            base_branch=str(base.get("ref") or "") or None,
            base_sha=base_sha,
            head_sha=head_sha,
            pr_number=int(pr.get("number") or payload.get("number") or 0) or None,
            from_fork=from_fork,
            sender_login=(sender.get("login") if isinstance(sender, dict) else None),
            sender_type=(sender.get("type") if isinstance(sender, dict) else None),
            default_branch=str(repo.get("default_branch") or "main"),
            title=pr.get("title"),
            draft=bool(pr.get("draft")),
            trigger=_PR_TRIGGERS.get(action, action),
        )
    except ValidationError as exc:
        raise EventRejected("malformed") from exc
