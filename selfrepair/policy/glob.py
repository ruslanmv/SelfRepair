"""Glob matching with `**` recursive wildcard.

Used by path-based policy rules. Rolling our own avoids a dep on `pathspec`
for a single matcher.
"""
from __future__ import annotations

import fnmatch


def matches(path: str, pattern: str) -> bool:
    """Match `path` against `pattern` with `**` as a recursive wildcard.

    `*` matches one path segment only; `**` matches zero or more segments.
    We always split into segments and recurse — using `fnmatch` on the
    full path would let `*` cross `/`, breaking `a/*.py` vs. `a/b/c.py`.

    Examples:
        matches("a.py", "*.py")                      -> True
        matches("a/b/c.py", "a/*.py")                -> False
        matches("a/b/c.py", "a/**")                  -> True
        matches("infra/prod/k8s.yaml", "infra/prod/**") -> True
    """
    return _match_parts(
        path.strip("/").split("/"),
        pattern.strip("/").split("/"),
    )


def _match_parts(path: list[str], pattern: list[str]) -> bool:
    if not pattern:
        return not path
    head, *rest = pattern
    if head == "**":
        if not rest:
            return True
        for i in range(len(path) + 1):
            if _match_parts(path[i:], rest):
                return True
        return False
    if not path:
        return False
    if not fnmatch.fnmatchcase(path[0], head):
        return False
    return _match_parts(path[1:], rest)
