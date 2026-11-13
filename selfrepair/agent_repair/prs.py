"""Draft pull requests for agent repairs. Draft only: an answer that is not a draft is treated as an error, and
there is no merge call anywhere in this package."""

from __future__ import annotations

from typing import Any, Protocol
from urllib.parse import urlsplit


class PullRequestError(Exception):
    pass


class PullRequests(Protocol):
    def open_draft(self, *, repo_url: str, head: str, base: str, title: str, body: str) -> dict[str, Any]: ...


class GitHubPullRequests:
    def __init__(self, token: str) -> None:
        self.token = token

    def open_draft(self, *, repo_url: str, head: str, base: str, title: str, body: str) -> dict[str, Any]:
        parts = urlsplit(repo_url)
        if (parts.hostname or "").lower() != "github.com":
            raise PullRequestError("draft pull requests are opened on github.com only in this release")
        full_name = parts.path.strip("/").removesuffix(".git")
        from github import Auth, Github

        gh = Github(auth=Auth.Token(self.token))
        try:
            pr = gh.get_repo(full_name).create_pull(title=title, body=body, head=head, base=base, draft=True)
        except Exception as exc:
            raise PullRequestError(f"GitHub refused the draft pull request: {exc}") from exc
        finally:
            gh.close()
        if not pr.draft:
            raise PullRequestError(f"GitHub opened #{pr.number} but not as a draft; it must be converted or closed by a person")
        return {"url": pr.html_url, "number": pr.number, "draft": True}
