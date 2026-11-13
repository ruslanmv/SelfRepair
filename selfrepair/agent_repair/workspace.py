"""Disposable workspaces for an agent repair: the repository at the exact base commit, the patch, the checks.

    clone_at      a new folder, the repository fetched and checked out at `base_commit`, HEAD verified; never a
                  fallback to another branch or commit
    apply_patch   `git apply --check`, then `git apply`; a patch made against a different commit is refused
    run_checks    the configured argv lists, no shell, a timeout each, credentials removed from the environment
    push_branch   commit on `langreplay/<attempt>` and push that one ref, never with --force
    remove        the folder is deleted afterwards

Paths are checked by `check_paths` before anything is applied: inside the approved scope, not absolute, no `..`,
not on SelfRepair's forbidden list (the same list reviewer remediation uses).
"""

from __future__ import annotations

import base64
import fnmatch
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from selfrepair.reviewer.remediation import _FORBIDDEN as FORBIDDEN

_GIT_DIFF = re.compile(r"^diff --git a/(\S+) b/(\S+)", re.M)
_HEADER = re.compile(r"^(?:\+\+\+|---) (?:[ab]/)?(\S+)", re.M)
_RENAME = re.compile(r"^rename (?:from|to) (\S+)", re.M)
_BINARY = re.compile(r"^Binary files (?:a/)?(\S+) and (?:b/)?(\S+) differ", re.M)
_SECRET_ENV = re.compile(r"(TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY|CREDENTIAL|_KEY$)", re.I)
TAIL = 2000


class WorkspaceError(Exception):
    """The workspace cannot be prepared, the patch is outside its scope, or git refused."""


def root() -> Path:
    base = os.environ.get("SELFREPAIR_SANDBOX_WORKDIR") or str(Path(tempfile.gettempdir()) / "selfrepair" / "sandbox")
    return Path(base) / "agent-repair"


def _git(*args: str, cwd: Path | None = None, env: dict[str, str] | None = None, timeout: int = 300) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, timeout=timeout, check=False)
    if proc.returncode != 0:
        raise WorkspaceError(f"git {args[0]} failed: {proc.stderr.decode('utf-8', 'replace').strip()[-400:]}")
    return proc.stdout.decode("utf-8", "replace").strip()


def patch_paths(patch: str) -> list[str]:
    found: list[str] = []
    for groups in (_GIT_DIFF.findall(patch), _BINARY.findall(patch)):
        for pair in groups:
            for p in pair:
                if p not in found:
                    found.append(p)
    for p in _HEADER.findall(patch) + _RENAME.findall(patch):
        if p != "/dev/null" and p not in found:
            found.append(p)
    return found


def check_paths(paths: list[str], scope: list[str]) -> list[str]:
    if not paths:
        raise WorkspaceError("the patch touches no file")
    for p in paths:
        pure = PurePosixPath(p)
        if pure.is_absolute() or ".." in pure.parts or p.startswith("~") or "\\" in p:
            raise WorkspaceError(f"the patch names a path outside the repository: {p}")
        name = pure.name
        if any(fnmatch.fnmatch(p, pattern) or p == pattern
               or (pattern.startswith("**/") and fnmatch.fnmatch(name, pattern[3:])) for pattern in FORBIDDEN):
            raise WorkspaceError(f"the patch changes a forbidden path: {p}")
        if not any(p == s or (s.endswith("/") and p.startswith(s)) for s in scope):
            raise WorkspaceError(f"the patch changes {p}, outside the approved scope ({', '.join(scope)})")
    return paths


def clone_at(repo_url: str, base_commit: str, into: Path) -> Path:
    if not re.fullmatch(r"[0-9a-f]{40}", base_commit):
        raise WorkspaceError("base_commit must be a full 40-character commit id")
    remove(into)
    into.mkdir(parents=True)
    _git("init", "-q", cwd=into)
    _git("remote", "add", "origin", repo_url, cwd=into)
    try:
        _git("fetch", "-q", "--depth", "1", "origin", base_commit, cwd=into)
    except WorkspaceError:
        _git("fetch", "-q", "origin", cwd=into)          # a server that does not serve a commit by id
    _git("checkout", "-q", "--detach", base_commit, cwd=into)
    head = _git("rev-parse", "HEAD", cwd=into)
    if head != base_commit:
        raise WorkspaceError(f"the workspace is at {head}, not the pinned base commit {base_commit}")
    return into


def apply_patch(ws: Path, patch: str) -> None:
    for args in (("apply", "--check", "--whitespace=nowarn", "-"), ("apply", "--whitespace=nowarn", "-")):
        proc = subprocess.run(["git", *args], cwd=ws, input=patch.encode("utf-8"), capture_output=True, timeout=60, check=False)
        if proc.returncode != 0:
            raise WorkspaceError("the patch does not apply to the pinned base commit: "
                                 + proc.stderr.decode("utf-8", "replace").strip()[-400:])


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not _SECRET_ENV.search(k)}


def run_checks(ws: Path, checks: list[list[str]], timeout_s: int) -> dict[str, Any]:
    if not checks:
        return {"status": "not_configured", "detail": "SELFREPAIR_AGENT_REPAIR_CHECKS is empty: no static check ran", "commands": []}
    results, ok = [], True
    for argv in checks:
        started = time.monotonic()
        try:
            proc = subprocess.run(argv, cwd=ws, env=_clean_env(), capture_output=True, timeout=timeout_s, check=False)
            code, out = proc.returncode, (proc.stdout + proc.stderr).decode("utf-8", "replace")
        except subprocess.TimeoutExpired as exc:
            code, out = 124, f"timed out after {timeout_s} s\n" + ((exc.stdout or b"") + (exc.stderr or b"")).decode("utf-8", "replace")
        except OSError as exc:
            code, out = 127, f"could not run: {exc}"
        results.append({"argv": argv, "exit": code, "seconds": round(time.monotonic() - started, 2), "tail": out[-TAIL:]})
        ok = ok and code == 0
    detail = ", ".join(f"{' '.join(r['argv'])}: exit {r['exit']}" for r in results)
    return {"status": "passed" if ok else "failed", "detail": detail, "commands": results}


def push_branch(ws: Path, *, branch: str, message: str, remote_url: str, token: str | None) -> str:
    if not re.fullmatch(r"langreplay/[A-Za-z0-9._-]+", branch):
        raise WorkspaceError(f"refusing to push {branch}: only langreplay/<attempt> branches are pushed")
    _git("checkout", "-q", "-b", branch, cwd=ws)
    _git("add", "-A", cwd=ws)
    _git("-c", "user.name=SelfRepair", "-c", "user.email=selfrepair@users.noreply.github.com",
         "commit", "-q", "-m", message, cwd=ws)
    env = dict(os.environ)
    parts = urlsplit(remote_url)
    if token and parts.scheme == "https":
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        # through the environment, so the token never appears in a process's arguments; appended to any git
        # configuration already passed this way
        n = int(env.get("GIT_CONFIG_COUNT") or 0)
        env.update({"GIT_CONFIG_COUNT": str(n + 1), f"GIT_CONFIG_KEY_{n}": f"http.{parts.scheme}://{parts.hostname}/.extraheader",
                    f"GIT_CONFIG_VALUE_{n}": f"AUTHORIZATION: basic {basic}"})
    _git("push", "origin", f"HEAD:refs/heads/{branch}", cwd=ws, env=env, timeout=300)
    return _git("rev-parse", "HEAD", cwd=ws)


def remove(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, onerror=lambda fn, p, exc: (os.chmod(p, 0o700), fn(p)))
