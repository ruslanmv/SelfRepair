"""How a review reads on a pull request.

The "codex" style follows the conventions developers already know from
hosted AI reviewers:

* one status comment on the pull request, edited in place, with a table of
  the latest review activity (status, reviewed commit, what triggered it);
* a pull-request review titled "💡 SelfRepair Review" that names the reviewed
  commit;
* one inline comment per finding, led by a P0-P3 priority badge and a bold
  one-line title, ending with "Useful? React with 👍 / 👎." so reactions can be
  collected as feedback.

Everything here is pure string building. No I/O.
"""
from __future__ import annotations

import html
import json
import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel

from selfrepair.reviewer.schemas import FindingRecord

Priority = Literal["P0", "P1", "P2", "P3"]

PRODUCT = "SelfRepair"
SUMMARY_MARKER = "<!-- selfrepair-review-summary"
FEEDBACK_PROMPT = "Useful? React with 👍 / 👎."

_PRIORITY_BY_SEVERITY: dict[str, Priority] = {
    "critical": "P0",
    "high": "P1",
    "medium": "P2",
    "low": "P3",
    "info": "P3",
}
_BADGE_COLOR: dict[str, str] = {"P0": "red", "P1": "orange", "P2": "yellow", "P3": "blue"}
_PRIORITY_RANK: dict[str, int] = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
_MAX_ROWS = 5


class PublishOptions(BaseModel):
    """Presentation choices taken from the repository's reviewer config."""

    style: Literal["codex", "classic"] = "codex"
    inline_comments: bool = True
    min_inline_priority: Priority = "P2"
    max_inline_comments: int = 10


def priority(severity: str) -> Priority:
    return _PRIORITY_BY_SEVERITY.get(severity, "P3")


def inline_allowed(finding: FindingRecord, options: PublishOptions) -> bool:
    """Inline comments are for findings at or above the configured priority."""
    if not options.inline_comments:
        return False
    return _PRIORITY_RANK[priority(finding.severity)] <= _PRIORITY_RANK[options.min_inline_priority]


def badge(level: str) -> str:
    color = _BADGE_COLOR.get(level, "lightgrey")
    return f"![{level} Badge](https://img.shields.io/badge/{level}-{color}?style=flat)"


def short_sha(sha: str) -> str:
    return (sha or "")[:10]


def inline_comment(finding: FindingRecord) -> str:
    """One finding, the way it appears on the changed line."""
    level = priority(finding.severity)
    title = _one_line(finding.title)
    parts = [f"**<sub><sub>{badge(level)}</sub></sub>  {title}**", "", finding.description.strip()]
    if finding.suggested_fix:
        parts += ["", f"**Suggested fix:** {finding.suggested_fix.strip()}"]
    parts += ["", FEEDBACK_PROMPT, "", f"<!-- sr-finding:{finding.fingerprint} -->"]
    return "\n".join(parts)


def review_body(
    head_sha: str,
    findings: list[FindingRecord],
    *,
    posted_inline: int,
    incomplete: str | None = None,
) -> str:
    """The pull-request review that carries the inline comments.

    `incomplete` is the reason the review could not finish. Then the body never
    claims a clean result: it says what was not reviewed.
    """
    lines = [f"### 💡 {PRODUCT} Review", ""]
    if incomplete:
        lines += [
            "⚠️ **Couldn't finish reviewing this commit**, so this is not a clean result: "
            "parts of the change may not have been reviewed.",
            "",
            f"Reason: {_one_line(incomplete)[:300]}",
            "",
        ]
    if not findings:
        if not incomplete:
            lines += ["Didn't find any major issues. 🚀", ""]
    elif posted_inline:
        lines += ["Here are some automated review suggestions for this pull request.", ""]
    else:
        lines += [
            "Here are some automated review suggestions for this pull request. "
            "They are listed below because the lines are outside this pull request's diff "
            "or below the inline priority.",
            "",
        ]
        for finding in findings:
            where = f" — `{finding.file_path}:{finding.start_line}`" if finding.file_path else ""
            lines.append(f"- **{priority(finding.severity)}** {_one_line(finding.title)}{where}")
        lines.append("")
    lines += [f"Reviewed commit: `{short_sha(head_sha)}`", "", _about()]
    return "\n".join(lines)


def _about() -> str:
    return (
        "<details> <summary>ℹ️ About " + PRODUCT + " in GitHub</summary>\n<br/>\n\n"
        f"{PRODUCT} reviews pull requests when they are opened or marked ready for review. "
        "Comment `@selfrepair review` to review the latest commit again, or "
        "`@selfrepair fix` to ask GitPilot for a draft pull request that addresses "
        "the open suggestions. A person merges; "
        f"{PRODUCT} never approves or merges.\n\n"
        "React with 👍 or 👎 on a suggestion to tell us whether it was useful.\n"
        "</details>"
    )


# ── status comment ────────────────────────────────────────────────────────────

_STATUS_TEXT = {
    "in_progress": "🔄 Running",
    "completed": "✅ Completed",
    "incomplete": "⚠️ Incomplete",
    "skipped": "⏭️ Skipped",
    "failed": "❌ Failed",
}


def summary_row(*, status: str, head_sha: str, trigger: str | None, at: datetime | None = None) -> dict[str, str]:
    stamp = (at or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "status": status if status in _STATUS_TEXT else "completed",
        "at": stamp,
        "commit": short_sha(head_sha)[:7],
        "trigger": _one_line(trigger or "PR opened")[:80],
    }


def summary_comment(rows: list[dict[str, str]]) -> str:
    """The pull-request status comment. `rows` is newest first.

    Same shape as the hosted reviewers' status comment: a collapsed block whose
    summary line carries the latest status, bold status text, and GitHub's
    `<relative-time>` element so the time reads "2 minutes ago" / "last week".
    """
    rows = [_clean_row(r) for r in rows][:_MAX_ROWS]
    latest = _STATUS_TEXT[rows[0]["status"]] if rows else _STATUS_TEXT["completed"]
    lines = [
        "<details>",
        f"<summary><strong>{PRODUCT} Review Summary</strong>: {latest}</summary>",
        "",
        f"This comment shows the latest {PRODUCT} review activity on this pull request.",
        "",
        "| Review | Status | Commit | Review trigger |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        icon, word = _STATUS_TEXT[row["status"]].split(" ", 1)
        since = " since" if row["status"] == "in_progress" else ""
        when = f'<relative-time datetime="{row["at"]}">{row["at"]}</relative-time>' if row["at"] else ""
        lines.append(
            f"| 📝 **Code Review** | {icon} **{word}**{since} {when} "
            f"| `{row['commit']}` | {row['trigger']} |"
        )
    lines += ["", _about(), "", "</details>", "",
              f"{SUMMARY_MARKER} {json.dumps({'rows': rows})} -->"]
    return "\n".join(lines)


def rows_from_comment(body: str) -> list[dict[str, str]]:
    """Read back the rows stored in our own status comment. Anything odd is dropped."""
    match = re.search(re.escape(SUMMARY_MARKER) + r" (\{.*?\}) -->", body or "", re.S)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except ValueError:
        return []
    rows = data.get("rows") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return []
    return [_clean_row(r) for r in rows if isinstance(r, dict)][:_MAX_ROWS]


def merge_row(rows: list[dict[str, str]], row: dict[str, str]) -> list[dict[str, str]]:
    """Newest first; an in-progress row for the same commit is replaced."""
    rest = [r for r in rows if not (r["commit"] == row["commit"] and r["status"] == "in_progress")]
    return [row, *rest][:_MAX_ROWS]


def _clean_row(row: dict[str, Any]) -> dict[str, str]:
    status = str(row.get("status") or "completed")
    commit = re.sub(r"[^0-9a-f]", "", str(row.get("commit") or "").lower())[:10]
    return {
        "status": status if status in _STATUS_TEXT else "completed",
        "at": re.sub(r"[^0-9:TZ\-]", "", str(row.get("at") or ""))[:20],
        "commit": commit,
        "trigger": _one_line(str(row.get("trigger") or ""))[:80],
    }


def _one_line(text: str) -> str:
    """Markdown-table and heading safe: one line, no pipes, no HTML."""
    text = html.escape(" ".join(str(text).split()), quote=False)
    return text.replace("|", "\\|")
