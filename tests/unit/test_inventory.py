from __future__ import annotations

from selfrepair.models import RepoRef


def test_repo_ref_defaults(sample_repo: RepoRef):
    assert sample_repo.default_branch == "main"
