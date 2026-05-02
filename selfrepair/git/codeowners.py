"""GitHub CODEOWNERS parser and matcher.

File lives at one of: CODEOWNERS, .github/CODEOWNERS, docs/CODEOWNERS,
.gitlab/CODEOWNERS. Format::

    # comment
    path/pattern    @user @org/team

Last matching rule wins (GitHub semantics). Patterns are gitignore-flavored
gitignore.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from selfrepair.policy.glob import matches as glob_matches

logger = logging.getLogger(__name__)

_CODEOWNERS_LOCATIONS = (
    "CODEOWNERS",
    ".github/CODEOWNERS",
    "docs/CODEOWNERS",
    ".gitlab/CODEOWNERS",
)


@dataclass(frozen=True)
class CodeOwnerRule:
    pattern: str
    owners: tuple[str, ...]


def find_codeowners(repo_root: Path) -> Path | None:
    for relative in _CODEOWNERS_LOCATIONS:
        candidate = repo_root / relative
        if candidate.is_file():
            return candidate
    return None


def parse(content: str) -> list[CodeOwnerRule]:
    rules: list[CodeOwnerRule] = []
    for raw in content.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        tokens = line.split()
        if len(tokens) < 2:
            logger.debug("codeowners: skipping malformed line %r", line)
            continue
        pattern, *owners = tokens
        rules.append(CodeOwnerRule(pattern=pattern, owners=tuple(owners)))
    return rules


def owners_for(paths: list[str], rules: list[CodeOwnerRule]) -> set[str]:
    """Return the union of owners that own the given paths.

    GitHub semantics: last matching rule wins per file. We collect owners
    from the winning rule for each path and union them.
    """
    result: set[str] = set()
    for path in paths:
        winning: CodeOwnerRule | None = None
        for rule in rules:
            if _path_matches(path, rule.pattern):
                winning = rule
        if winning is not None:
            result.update(winning.owners)
    return result


def _path_matches(path: str, pattern: str) -> bool:
    """CODEOWNERS-style match.

    Common subset:
      - leading `/`  : anchor at root
      - trailing `/` : directory-only (treat as `pattern**`)
      - `**`         : recursive wildcard
      - else         : pattern matches anywhere in the path

    Complex git pathspecs are rare in CODEOWNERS files; we cover the 90%.
    """
    rooted = pattern.startswith("/")
    if rooted:
        pattern = pattern.lstrip("/")
    if pattern.endswith("/"):
        pattern = pattern + "**"

    if rooted:
        return glob_matches(path, pattern)

    if glob_matches(path, pattern):
        return True

    parts = path.split("/")
    for i in range(1, len(parts)):
        if glob_matches("/".join(parts[i:]), pattern):
            return True
    return False
