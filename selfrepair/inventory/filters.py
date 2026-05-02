from __future__ import annotations

from selfrepair.models import RepoRef


def include_repo(repo: RepoRef) -> bool:
    return not repo.archived
