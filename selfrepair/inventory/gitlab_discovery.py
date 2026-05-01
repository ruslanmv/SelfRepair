from __future__ import annotations

import logging

import httpx

from selfrepair.models import RepoRef
from selfrepair.settings import Settings

logger = logging.getLogger(__name__)


class GitLabDiscovery:
    """Discover repositories from a GitLab instance (gitlab.com or self-hosted)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def list_repositories(self) -> list[RepoRef]:
        if not self.settings.gitlab_token:
            return []
        if not self.settings.gitlab_group and not self.settings.gitlab_user:
            return []

        base = self.settings.gitlab_url.rstrip("/")
        headers = {"PRIVATE-TOKEN": self.settings.gitlab_token}
        repos: list[RepoRef] = []

        try:
            if self.settings.gitlab_group:
                url = f"{base}/api/v4/groups/{self.settings.gitlab_group}/projects"
            else:
                url = f"{base}/api/v4/users/{self.settings.gitlab_user}/projects"

            params: dict = {"per_page": 100, "page": 1}
            if not self.settings.gitlab_include_private:
                params["visibility"] = "public"

            while True:
                resp = httpx.get(url, headers=headers, params=params, timeout=30)
                resp.raise_for_status()
                projects = resp.json()
                if not projects:
                    break
                for proj in projects:
                    repos.append(
                        RepoRef(
                            name=proj["path"],
                            full_name=proj["path_with_namespace"],
                            clone_url=proj.get("http_url_to_repo", proj.get("ssh_url_to_repo", "")),
                            default_branch=proj.get("default_branch", "main"),
                            archived=proj.get("archived", False),
                            private=proj.get("visibility", "private") == "private",
                            platform="gitlab",
                            kind="code",
                            namespace=proj.get("namespace", {}).get("full_path"),
                            web_url=proj.get("web_url"),
                        )
                    )
                params["page"] += 1
        except Exception as exc:
            logger.warning("GitLab discovery failed: %s", exc)

        return repos
