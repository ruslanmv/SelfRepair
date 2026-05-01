from __future__ import annotations

try:
    from huggingface_hub import HfApi
except Exception:
    HfApi = None  # type: ignore[assignment]

from selfrepair.models import RepoRef
from selfrepair.settings import Settings


class HuggingFaceDiscovery:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = HfApi(token=settings.hf_token) if HfApi else None

    def list_repositories(self) -> list[RepoRef]:
        if not self.settings.hf_namespace or self.client is None:
            return []

        repos: list[RepoRef] = []
        for repo_type in self.settings.hf_repo_type_list:
            for repo in self.client.list_repos_objs(author=self.settings.hf_namespace, repo_type=repo_type):
                repos.append(
                    RepoRef(
                        name=repo.id.split("/")[-1],
                        full_name=repo.id,
                        clone_url=f"https://huggingface.co/{repo.id}",
                        default_branch="main",
                        private=getattr(repo, "private", False),
                        platform="huggingface",
                        kind="space" if repo_type == "space" else repo_type if repo_type in {"model", "dataset"} else "unknown",
                        namespace=self.settings.hf_namespace,
                        web_url=f"https://huggingface.co/{repo.id}",
                    )
                )
        return repos
