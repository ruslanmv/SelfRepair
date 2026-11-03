"""Shared fixtures for reviewer unit tests."""
from __future__ import annotations

import uuid

from selfrepair.reviewer.schemas import RepoBinding
from selfrepair.reviewer.store import MemoryReviewStore

ORG = uuid.UUID("00000000-0000-0000-0000-0000000000aa")
REPO = uuid.UUID("00000000-0000-0000-0000-0000000000bb")


def binding(**overrides: object) -> RepoBinding:
    data = {
        "org_id": ORG,
        "repo_id": REPO,
        "provider": "github",
        "full_name": "octo/demo",
        "default_branch": "main",
        "config_yaml": "version: 1\nreviewer:\n  enabled: true\n",
        "installation_id": 99,
    }
    data.update(overrides)
    return RepoBinding(**data)  # type: ignore[arg-type]


def store_with_repo(**overrides: object) -> MemoryReviewStore:
    return MemoryReviewStore(repos=[binding(**overrides)])


VULN_DIFF = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,5 @@
 def run(cmd):
+    password = "supersecretvalue"
+    return eval(cmd)
     return cmd
"""

CLEAN_DIFF = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,3 @@
 def add(a, b):
+    return a + b
     return 0
"""
