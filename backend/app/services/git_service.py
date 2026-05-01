from __future__ import annotations

import re
from urllib.parse import urlparse

from selfrepair.models import RepoRef


class GitService:
    """Normalizes repository URLs into RepoRef metadata."""

    def build_repo_ref(self, repo_url: str, branch: str = "main") -> RepoRef:
        repo_url = repo_url.strip()
        if not repo_url:
            raise ValueError("repo_url is required")
        owner, name, platform = _parse_repo_url(repo_url)
        return RepoRef(
            name=name,
            full_name=f"{owner}/{name}",
            clone_url=repo_url,
            default_branch=branch,
            platform=platform,
            kind="code",
            namespace=owner,
            web_url=repo_url,
        )


def _parse_repo_url(repo_url: str) -> tuple[str, str, str]:
    # Supports https://github.com/owner/repo(.git) and git@github.com:owner/repo.git
    if repo_url.startswith("git@"):
        match = re.match(r"git@(?P<host>[^:]+):(?P<owner>[^/]+)/(?P<repo>.+?)(?:\.git)?$", repo_url)
        if not match:
            raise ValueError("Unsupported SSH repository URL")
        host = match.group("host")
        owner = match.group("owner")
        name = match.group("repo").removesuffix(".git")
    else:
        parsed = urlparse(repo_url)
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2:
            raise ValueError("Repository URL must include owner and repository name")
        host = parsed.netloc
        owner, name = parts[-2], parts[-1].removesuffix(".git")
    platform = "gitlab" if "gitlab" in host else "github"
    return owner, name, platform
