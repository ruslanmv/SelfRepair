from __future__ import annotations

from github import Github


def create_issue(token: str | None, repo_full_name: str, title: str, body: str) -> str:
    client = Github(token) if token else Github()
    repo = client.get_repo(repo_full_name)
    issue = repo.create_issue(title=title, body=body)
    return issue.html_url
