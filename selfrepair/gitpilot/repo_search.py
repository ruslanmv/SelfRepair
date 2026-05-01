from __future__ import annotations

from github import Github


def search_open_prs(token: str | None, query: str) -> list[str]:
    client = Github(token) if token else Github()
    return [item.html_url for item in client.search_issues(query=query)]
