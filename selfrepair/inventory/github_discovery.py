from __future__ import annotations

try:
    from github import Github
    from github.GithubException import GithubException
except Exception:
    Github = None  # type: ignore[assignment]
    class GithubException(Exception):
        pass

from selfrepair.models import RepoRef
from selfrepair.settings import Settings


class GitHubOrgDiscovery:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = Github(settings.github_token) if (settings.github_token and Github) else (Github() if Github else None)

    def _convert_repo(self, repo) -> RepoRef:
        owner = getattr(repo.owner, "login", None)
        return RepoRef(
            name=repo.name,
            full_name=repo.full_name,
            clone_url=repo.clone_url,
            default_branch=repo.default_branch or self.settings.github_base_branch,
            archived=repo.archived,
            private=repo.private,
            platform="github",
            kind="code",
            namespace=owner,
            web_url=getattr(repo, "html_url", None),
        )

    def list_repositories(self) -> list[RepoRef]:
        if self.client is None:
            return []
        repos: list[RepoRef] = []
        if self.settings.github_org:
            try:
                org = self.client.get_organization(self.settings.github_org)
                repos.extend(self._convert_repo(repo) for repo in org.get_repos())
            except GithubException as exc:
                raise RuntimeError(f"Failed to list GitHub org repositories: {exc}") from exc
        elif self.settings.github_user:
            try:
                user = self.client.get_user(self.settings.github_user)
                repos.extend(self._convert_repo(repo) for repo in user.get_repos())
            except GithubException as exc:
                raise RuntimeError(f"Failed to list GitHub user repositories: {exc}") from exc
        return repos
