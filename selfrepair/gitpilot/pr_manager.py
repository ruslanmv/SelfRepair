from __future__ import annotations

from git import Repo
from github import Github

from selfrepair.constants import STANDARD_COMMIT_MESSAGE
from selfrepair.settings import Settings


class PullRequestManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = Github(settings.github_token) if settings.github_token else Github()

    def commit_push_and_open_pr(
        self,
        repo_full_name: str,
        repo_dir,
        branch_name: str,
        base_branch: str,
        title: str | None = None,
        body: str | None = None,
    ) -> str | None:
        repo = Repo(repo_dir)
        repo.git.checkout("-B", branch_name)
        repo.git.add(A=True)
        if not repo.is_dirty(untracked_files=True):
            return None
        repo.index.commit(STANDARD_COMMIT_MESSAGE)

        if self.settings.allow_direct_push:
            origin = repo.remote(name="origin")
            origin.push(refspec=f"{branch_name}:{branch_name}", force=True)

        if not self.settings.allow_autofix_pr:
            return None

        gh_repo = self.client.get_repo(repo_full_name)
        pr = gh_repo.create_pull(
            title=title or STANDARD_COMMIT_MESSAGE,
            body=body or "Automated standards and health maintenance update.",
            head=branch_name,
            base=base_branch,
        )
        return pr.html_url
