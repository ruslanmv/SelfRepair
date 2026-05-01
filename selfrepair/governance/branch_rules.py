from __future__ import annotations

import re


def build_branch_name(repo_name: str) -> str:
    safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "-", repo_name).strip("-").lower()
    return f"repoguardian/repair/{safe_name}"
