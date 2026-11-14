"""Diff collection and line validation.

Inline comments are legal only on lines this module extracted from a real
patch. A model-supplied line that is not in the diff is rejected.
"""
from __future__ import annotations

import re

from selfrepair.reviewer.schemas import ZERO_SHA, DiffFile, DiffLine, DiffSet, ReviewEvent

_MAX_FILES = 200
_MAX_PATCH_CHARS = 600_000

# Files no person writes by hand. Reviewing them wastes the budget and the
# model cannot say anything useful about a minified bundle.
_LOCKFILES = frozenset({
    "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb",
    "poetry.lock", "uv.lock", "pdm.lock", "Pipfile.lock", "Cargo.lock", "go.sum",
    "composer.lock", "Gemfile.lock", "mix.lock", "flake.lock", "packages.lock.json",
})
_GENERATED = re.compile(
    r"(^|/)(node_modules|vendor|dist|\.next|\.nuxt|__snapshots__)/"
    r"|(^|/)build/.*\.(js|mjs|cjs|css|html|map)$"
    r"|\.min\.(js|css|mjs)$"
    r"|\.(js|css|mjs)\.map$|\.map$"
    r"|(^|/)assets/[^/]+-[A-Za-z0-9_-]{8,}\.(js|mjs|css)$"   # hashed bundler output
    r"|_pb2(_grpc)?\.py$|\.pb\.go$|\.generated\.\w+$"
)


def is_generated(path: str) -> bool:
    """True for lockfiles, build output, bundles and source maps."""
    name = path.rsplit("/", 1)[-1]
    return name in _LOCKFILES or bool(_GENERATED.search(path))


def parse_unified_diff(text: str) -> list[DiffFile]:
    """Parse a unified diff into files and commentable lines.

    Additions are `RIGHT` lines in the new file. Deletions are `LEFT` lines
    in the old file. Context lines are kept so a comment can cite them only
    when they sit inside a changed hunk; GitHub accepts comments on changed
    lines and the immediate hunk, and we only mark `+` and `-` lines so a
    comment cannot land on an untouched line.
    """
    files: list[DiffFile] = []
    current: DiffFile | None = None
    old_line = 0
    new_line = 0
    for raw in text.splitlines():
        if raw.startswith("diff --git "):
            current = _start_file(raw)
            files.append(current)
            continue
        if current is None:
            continue
        if raw.startswith("Binary files ") or raw.startswith("GIT binary patch"):
            current.status = "binary"
            current.patch = ""
            continue
        if raw.startswith("--- ") or raw.startswith("+++ ") or raw.startswith("index "):
            if raw.startswith("rename from "):
                current.previous_path = raw[len("rename from ") :]
            continue
        if raw.startswith("rename from "):
            current.previous_path = raw[len("rename from ") :]
            current.status = "renamed"
            continue
        if raw.startswith("rename to "):
            current.path = raw[len("rename to ") :]
            continue
        if raw.startswith("new file"):
            current.status = "added"
            continue
        if raw.startswith("deleted file"):
            current.status = "removed"
            continue
        if raw.startswith("@@"):
            old_line, new_line = _hunk_start(raw)
            current.patch += raw + "\n"
            continue
        if raw.startswith("+"):
            current.patch += raw + "\n"
            current.lines.append(
                DiffLine(path=current.path, line=new_line, side="RIGHT", text=raw[1:])
            )
            new_line += 1
            continue
        if raw.startswith("-"):
            current.patch += raw + "\n"
            current.lines.append(
                DiffLine(path=current.path, line=old_line, side="LEFT", text=raw[1:])
            )
            old_line += 1
            continue
        if raw.startswith("\\"):
            continue
        # Context line. Advance both counters and do not mark it commentable.
        if current.patch:
            current.patch += raw + "\n"
        if raw.startswith(" "):
            old_line += 1
            new_line += 1
    return files


def parse_github_files(files: list[dict]) -> list[DiffFile]:
    """Parse the `files` array from the GitHub compare or pulls API."""
    parsed: list[DiffFile] = []
    for item in files:
        filename = item.get("filename") or ""
        if not filename:
            continue
        status = _github_status(str(item.get("status") or "modified"))
        patch = item.get("patch") or ""
        if status == "binary" or not patch:
            parsed.append(
                DiffFile(
                    path=filename,
                    previous_path=item.get("previous_filename"),
                    status="binary" if not patch and status != "removed" else status,
                    patch="",
                )
            )
            if status == "removed":
                parsed[-1].status = "removed"
            continue
        from_patch = parse_unified_diff(
            f"diff --git a/{filename} b/{filename}\n--- a/{filename}\n+++ b/{filename}\n{patch}\n"
        )
        if not from_patch:
            continue
        file = from_patch[0]
        file.path = filename
        file.previous_path = item.get("previous_filename")
        file.status = status
        parsed.append(file)
    return parsed


def limit_diff(files: list[DiffFile]) -> DiffSet:
    """Cap review input. Truncation is reported; it is not a successful review."""
    kept: list[DiffFile] = []
    skipped = [item.path for item in files if is_generated(item.path)]
    files = [item for item in files if not is_generated(item.path)]
    used = 0
    truncated = False
    for item in files:
        if len(kept) >= _MAX_FILES:
            truncated = True
            break
        patch = item.patch
        if used + len(patch) > _MAX_PATCH_CHARS:
            truncated = True
            patch = patch[: max(0, _MAX_PATCH_CHARS - used)]
            item = item.model_copy(update={"patch": patch})
            kept.append(item)
            break
        used += len(patch)
        kept.append(item)
    return DiffSet(files=kept, truncated=truncated, source="patch", skipped=skipped)


def line_allowed(diff: DiffSet, path: str | None, line: int | None, side: str | None) -> bool:
    """Return True when a finding cites a real changed line, or a whole changed file."""
    if not path:
        return False
    match = next((item for item in diff.files if item.path == path), None)
    if match is None:
        return False
    if line is None:
        return True
    wanted = side or "RIGHT"
    return any(entry.line == line and entry.side == wanted for entry in match.lines)


def empty_range(event: ReviewEvent) -> bool:
    """A push with no commits and identical SHAs has nothing to review."""
    if event.deleted:
        return False
    return event.base_sha == event.head_sha or (
        event.base_sha != ZERO_SHA and event.head_sha != ZERO_SHA and not event.commits and event.base_sha == event.head_sha
    )


def _start_file(header: str) -> DiffFile:
    # diff --git a/path b/path
    parts = header.split(" ")
    path = "unknown"
    if len(parts) >= 4:
        path = parts[-1]
        if path.startswith("b/"):
            path = path[2:]
    return DiffFile(path=path)


def _hunk_start(raw: str) -> tuple[int, int]:
    # @@ -l,s +l,s @@
    try:
        body = raw.split("@@")[1].strip()
        old_part, new_part = body.split(" ")[:2]
        old_line = int(old_part.split(",")[0].lstrip("-"))
        new_line = int(new_part.split(",")[0].lstrip("+"))
    except (IndexError, ValueError):
        return 1, 1
    return max(old_line, 1), max(new_line, 1)


def _github_status(status: str) -> str:
    mapping = {
        "added": "added",
        "modified": "modified",
        "removed": "removed",
        "renamed": "renamed",
        "copied": "added",
        "changed": "modified",
        "unchanged": "modified",
    }
    return mapping.get(status, "modified")  # type: ignore[return-value]
