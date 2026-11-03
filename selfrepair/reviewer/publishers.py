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


class HttpxTransport:
    """Small HTTP client used by the live diff provider and publishers."""

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout

    async def get(self, url: str, headers: dict[str, str]) -> Any:
        import httpx

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.get(url, headers=headers)

    async def post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> Any:
        import httpx

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.post(url, json=json, headers=headers)

    async def patch(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> Any:
        import httpx

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            return await client.patch(url, json=json, headers=headers)


class RecordingPublisher:
    """Captures publication payloads. Tests inject this so nothing leaves the process."""

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

    async def announce(self, *, event: ReviewEvent, run: RunRecord) -> None:
        """Record the in-progress check. Tests can see it; GitHub is not called."""
        del event
        self.sent.append(
            {
                "kind": "check",
                "status": "recorded",
                "body": {"name": CHECK_NAME, "head_sha": run.head_sha, "status": "in_progress"},
                "fingerprints": [],
            }
        )

    async def abandon(self, *, event: ReviewEvent, run: RunRecord, reason: str) -> None:
        """Record the terminal check a failed review would send."""
        del event
        self.sent.append(
            {
                "kind": "check",
                "status": "recorded",
                "body": {
                    "name": CHECK_NAME,
                    "head_sha": run.head_sha,
                    "status": "completed",
                    "conclusion": "action_required",
                    "output": {"title": "Review did not complete", "summary": reason[:1000]},
                },
                "fingerprints": [],
            }
        )


class UnpublishedPublisher:
    """Used when credentials are missing. The review is stored and the check is not sent."""

    def __init__(self, reason: str) -> None:
        self._reason = reason

    async def announce(self, *, event: ReviewEvent, run: RunRecord) -> None:
        del event, run

    async def abandon(self, *, event: ReviewEvent, run: RunRecord, reason: str) -> None:
        del event, run, reason

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
            item["status"] = "unpublished"
            item["error"] = self._reason
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
        # Check run created by `announce`, per review run. `publish` and
        # `abandon` complete that same check instead of creating a second one.
        self._announced: dict[str, str] = {}

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
                check_id = self._announced.pop(str(run.id), None)
                if check_id is not None:
                    response = await self._complete_check(
                        event, check_id, item["body"], headers
                    )
                    item = self._record(item, response, fallback_id=check_id)
                    results.append(item)
                    continue
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

    async def announce(self, *, event: ReviewEvent, run: RunRecord) -> None:
        """Post an in-progress check so branch protection does not see a missing check."""
        url = f"{self._api}/repos/{event.repo_full_name}/check-runs"
        body = {
            "name": CHECK_NAME,
            "head_sha": run.head_sha,
            "status": "in_progress",
            "output": {
                "title": "Review in progress",
                "summary": "SelfRepair is reviewing this revision.",
            },
        }
        response = await self._transport.post(url, json=body, headers=_headers_for(self._token))
        _raise_if_rate_limited(response)
        if getattr(response, "status_code", 0) < 400:
            check_id = _response_id(response)
            if check_id:
                self._announced[str(run.id)] = check_id

    async def abandon(self, *, event: ReviewEvent, run: RunRecord, reason: str) -> None:
        """Give the announced check a terminal result when the review failed.

        Without this a crash or a transient error after `announce` leaves the
        check `in_progress` forever, and each retry adds another one. Best
        effort: a failure here must not hide the original error.
        """
        check_id = self._announced.pop(str(run.id), None)
        if check_id is None:
            return
        body = {
            "name": CHECK_NAME,
            "status": "completed",
            "conclusion": "action_required",
            "output": {
                "title": "Review did not complete",
                "summary": (
                    "SelfRepair could not finish reviewing this revision "
                    f"({reason[:200]}). A retry posts a new result."
                ),
            },
        }
        try:
            await self._complete_check(event, check_id, body, _headers_for(self._token))
        except Exception:  # noqa: BLE001 - best effort, see docstring
            return

    async def _complete_check(
        self, event: ReviewEvent, check_id: str, body: dict[str, Any], headers: dict[str, str]
    ) -> Any:
        """PATCH the announced check. `head_sha` is not an update field."""
        url = f"{self._api}/repos/{event.repo_full_name}/check-runs/{check_id}"
        update = {key: value for key, value in body.items() if key != "head_sha"}
        patch = getattr(self._transport, "patch", None)
        if patch is None:  # transports without PATCH keep the old behaviour
            return await self._transport.post(
                f"{self._api}/repos/{event.repo_full_name}/check-runs", json=body, headers=headers
            )
        return await patch(url, json=update, headers=headers)

    @staticmethod
    def _record(item: dict[str, Any], response: Any, *, fallback_id: str) -> dict[str, Any]:
        status = getattr(response, "status_code", 0)
        if status == 429 or status == 403 and _rate_limited(response):
            raise TransientReviewError(f"github rate limited: {status}")
        if status >= 400:
            item["status"] = "failed"
            item["error"] = getattr(response, "text", "")[:500]
        else:
            item["status"] = "published"
            item["external_id"] = _response_id(response) or fallback_id
        return item


class GitLabHttpPublisher:
    """Post a commit status and one merge-request note. Does not approve or merge."""

    def __init__(self, transport: Any, token: str, api_url: str = "https://gitlab.com/api/v4") -> None:
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
        if event.project_id is None:
            return [
                {
                    "kind": "status",
                    "status": "unpublished",
                    "error": "gitlab project id missing",
                    "fingerprints": [],
                    "body": {},
                }
            ]
        payloads = build_payloads(
            event=event,
            run=run,
            findings=findings,
            conclusion=conclusion,
            summary=summary,
            already_published=already_published,
        )
        headers = {"PRIVATE-TOKEN": self._token}
        results: list[dict[str, Any]] = []
        project = event.project_id
        for item in payloads:
            if item["kind"] == "status":
                sha = item["body"]["sha"]
                url = f"{self._api}/projects/{project}/statuses/{sha}"
            elif item["kind"] == "discussion" and event.pr_number is not None:
                url = f"{self._api}/projects/{project}/merge_requests/{event.pr_number}/notes"
            else:
                continue
            response = await self._transport.post(url, json=item["body"], headers=headers)
            _raise_if_rate_limited(response)
            status = getattr(response, "status_code", 0)
            if status >= 400:
                item["status"] = "failed"
                item["error"] = getattr(response, "text", "")[:500]
            else:
                item["status"] = "published"
                body = response.json() if hasattr(response, "json") else {}
                item["external_id"] = str(body.get("id") or "")
            results.append(item)
        return results

    async def announce(self, *, event: ReviewEvent, run: RunRecord) -> None:
        """Post a pending commit status before analysis finishes."""
        if event.project_id is None:
            return
        url = f"{self._api}/projects/{event.project_id}/statuses/{run.head_sha}"
        body = {
            "sha": run.head_sha,
            "state": "pending",
            "context": CHECK_NAME,
            "description": "SelfRepair is reviewing this revision.",
        }
        response = await self._transport.post(
            url, json=body, headers={"PRIVATE-TOKEN": self._token}
        )
        _raise_if_rate_limited(response)


def _response_id(response: Any) -> str:
    try:
        body = response.json() if hasattr(response, "json") else {}
    except Exception:  # noqa: BLE001 - a non-JSON body has no id
        return ""
    return str((body or {}).get("id") or "") if isinstance(body, dict) else ""


def _headers_for(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _raise_if_rate_limited(response: Any) -> None:
    status = getattr(response, "status_code", 0)
    if status == 429 or (status == 403 and _rate_limited(response)):
        raise TransientReviewError(f"provider rate limited: {status}")


def _rate_limited(response: Any) -> bool:
    headers = getattr(response, "headers", {}) or {}
    remaining = headers.get("x-ratelimit-remaining")
    return remaining == "0"
