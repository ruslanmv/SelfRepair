"""Build and send review publications.

The check name is `SelfRepair / Review`. A review comment uses the COMMENT
event and never APPROVE, so the bot cannot satisfy a human approval rule.
Repeated fingerprints on the same pull request are not posted again.
"""
from __future__ import annotations

from typing import Any, Protocol

from selfrepair.reviewer.schemas import (
    CHECK_NAME,
    Conclusion,
    FindingRecord,
    ReviewEvent,
    RunRecord,
    TransientReviewError,
)

_ANNOTATION_LIMIT = 50


class Publisher(Protocol):
    """Sends check runs and review comments. Implementations must be idempotent."""

    async def publish(
        self,
        *,
        event: ReviewEvent,
        run: RunRecord,
        findings: list[FindingRecord],
        conclusion: Conclusion,
        summary: str,
        already_published: set[str],
    ) -> list[dict[str, Any]]: ...


class RecordingPublisher:
    """Captures publication payloads. Used by tests and when no token is configured."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def publish(
        self,
        *,
        event: ReviewEvent,
        run: RunRecord,
        findings: list[FindingRecord],
        conclusion: Conclusion,
        summary: str,
        already_published: set[str],
    ) -> list[dict[str, Any]]:
        payloads = build_payloads(
            event=event,
            run=run,
            findings=findings,
            conclusion=conclusion,
            summary=summary,
            already_published=already_published,
        )
        for item in payloads:
            item["status"] = "recorded"
        self.sent.extend(payloads)
        return payloads


def build_payloads(
    *,
    event: ReviewEvent,
    run: RunRecord,
    findings: list[FindingRecord],
    conclusion: Conclusion,
    summary: str,
    already_published: set[str],
) -> list[dict[str, Any]]:
    """Return the provider payloads for this run. Does not perform I/O."""
    fresh = [item for item in findings if item.fingerprint not in already_published]
    if event.provider == "gitlab":
        return [
            {
                "kind": "status",
                "body": gitlab_status_body(run, conclusion, summary),
                "fingerprints": [],
            },
            {
                "kind": "discussion",
                "body": gitlab_discussion_body(summary, fresh),
                "fingerprints": [item.fingerprint for item in fresh],
            },
        ]
    payloads: list[dict[str, Any]] = [
        {
            "kind": "check",
            "body": github_check_body(run, findings, conclusion, summary),
            "fingerprints": [item.fingerprint for item in findings],
        }
    ]
    if event.kind == "pull_request" and event.pr_number is not None:
        payloads.append(
            {
                "kind": "review",
                "body": github_review_body(run, summary, fresh),
                "fingerprints": [item.fingerprint for item in fresh],
            }
        )
    return payloads


def github_check_body(
    run: RunRecord,
    findings: list[FindingRecord],
    conclusion: Conclusion,
    summary: str,
) -> dict[str, Any]:
    """GitHub Check Run body. Annotations are capped at the API batch limit."""
    annotations = []
    for finding in findings:
        if not finding.file_path or finding.start_line is None:
            continue
        if len(annotations) >= _ANNOTATION_LIMIT:
            break
        annotations.append(
            {
                "path": finding.file_path,
                "start_line": finding.start_line,
                "end_line": finding.end_line or finding.start_line,
                "annotation_level": _annotation_level(finding.severity),
                "message": _comment(finding)[:60000],
                "title": finding.title[:255],
            }
        )
    title = _title(conclusion, len(findings))
    return {
        "name": CHECK_NAME,
        "head_sha": run.head_sha,
        "status": "completed",
        "conclusion": conclusion,
        "output": {
            "title": title,
            "summary": summary[:65000],
            "annotations": annotations,
        },
    }


def github_review_body(
    run: RunRecord, summary: str, findings: list[FindingRecord]
) -> dict[str, Any]:
    """Pull request review. `event` is COMMENT, never APPROVE or REQUEST_CHANGES."""
    comments = []
    for finding in findings:
        if finding.side != "RIGHT" or not finding.file_path or finding.start_line is None:
            continue
        comments.append(
            {
                "path": finding.file_path,
                "line": finding.start_line,
                "side": "RIGHT",
                "body": _comment(finding),
            }
        )
    return {
        "commit_id": run.head_sha,
        "event": "COMMENT",
        "body": summary[:65000],
        "comments": comments,
    }


def gitlab_status_body(run: RunRecord, conclusion: Conclusion, summary: str) -> dict[str, Any]:
    """GitLab commit status. An incomplete review is failed, not success."""
    state = {
        "success": "success",
        "failure": "failed",
        "action_required": "failed",
        "neutral": "canceled",
        "cancelled": "canceled",
    }[conclusion]
    return {
        "sha": run.head_sha,
        "state": state,
        "context": CHECK_NAME,
        "description": summary[:255],
    }


def gitlab_discussion_body(summary: str, findings: list[FindingRecord]) -> dict[str, Any]:
    """A single MR note. GitLab line discussions are only included for RIGHT lines."""
    lines = [summary, ""]
    for finding in findings:
        lines.append(_comment(finding))
        lines.append("")
    return {"body": "\n".join(lines).strip()}


def _comment(finding: FindingRecord) -> str:
    where = ""
    if finding.file_path and finding.start_line:
        where = f" `{finding.file_path}:{finding.start_line}`"
    evidence = f"\n\nEvidence: `{finding.evidence}`" if finding.evidence else ""
    fix = f"\n\nSuggested fix: {finding.suggested_fix}" if finding.suggested_fix else ""
    return (
        f"**{finding.severity}** {finding.title}{where}\n\n"
        f"{finding.description}{evidence}{fix}\n\n"
        f"<!-- sr-finding:{finding.fingerprint} -->"
    )


def _title(conclusion: Conclusion, count: int) -> str:
    if conclusion == "success":
        return "Review passed" if count == 0 else f"Review passed with {count} note(s)"
    if conclusion == "failure":
        return f"Review found {count} blocking finding(s)"
    if conclusion == "action_required":
        return "Review incomplete"
    return "Review skipped"


def _annotation_level(severity: str) -> str:
    if severity in {"critical", "high"}:
        return "failure"
    if severity == "medium":
        return "warning"
    return "notice"


class GitHubHttpPublisher:
    """POST check runs and pull-request reviews with an installation token.

    `transport` is an object with `async post(url, json, headers) -> response`.
    A 429 raises `TransientReviewError` so the worker retries.
    """

    def __init__(self, transport: Any, token: str, api_url: str = "https://api.github.com") -> None:
        self._transport = transport
        self._token = token
        self._api = api_url.rstrip("/")

    async def publish(
        self,
        *,
        event: ReviewEvent,
        run: RunRecord,
        findings: list[FindingRecord],
        conclusion: Conclusion,
        summary: str,
        already_published: set[str],
    ) -> list[dict[str, Any]]:
        payloads = build_payloads(
            event=event,
            run=run,
            findings=findings,
            conclusion=conclusion,
            summary=summary,
            already_published=already_published,
        )
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        results: list[dict[str, Any]] = []
        for item in payloads:
            if item["kind"] == "check":
                url = f"{self._api}/repos/{event.repo_full_name}/check-runs"
            elif item["kind"] == "review" and event.pr_number is not None:
                url = (
                    f"{self._api}/repos/{event.repo_full_name}/pulls/"
                    f"{event.pr_number}/reviews"
                )
            else:
                continue
            response = await self._transport.post(url, json=item["body"], headers=headers)
            status = getattr(response, "status_code", 0)
            if status == 429 or status == 403 and _rate_limited(response):
                raise TransientReviewError(f"github rate limited: {status}")
            if status >= 400:
                item["status"] = "failed"
                item["error"] = getattr(response, "text", "")[:500]
            else:
                item["status"] = "published"
                body = response.json() if hasattr(response, "json") else {}
                item["external_id"] = str(body.get("id") or "")
            results.append(item)
        return results


def _rate_limited(response: Any) -> bool:
    headers = getattr(response, "headers", {}) or {}
    remaining = headers.get("x-ratelimit-remaining")
    return remaining == "0"
