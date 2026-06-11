"""Real repository health checks via the GitHub REST API (no cloning).

Given a repo URL + branch, this fetches repo metadata and the file tree from
``api.github.com`` and runs a set of lightweight hygiene detectors, producing
a health score and an issues list. It NEVER writes to the target repo
(dry-run only) and never reads ``HF_TOKEN``.

The worker runs in a daemon thread that opens its own ``SessionLocal`` (same
pattern as ``scanner.py``) so it never blocks the request thread.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from datetime import datetime, timedelta, timezone

import httpx

from .database import Job, Message, Notification, SessionLocal

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
_STALE_DAYS = 180

# Detector severity weights for scoring.
_WEIGHTS = {"high": 25, "medium": 12, "low": 5}


def parse_owner_repo(repo_url: str) -> tuple[str | None, str | None]:
    """Extract (owner, repo) from a GitHub URL or ``owner/repo`` shorthand."""
    if not repo_url:
        return None, None
    s = repo_url.strip()
    # Strip scheme/host and trailing .git
    m = re.search(r"github\.com[:/]+([^/]+)/([^/#?]+)", s)
    if not m:
        # Accept bare "owner/repo"
        m = re.match(r"^([^/\s]+)/([^/\s#?]+)$", s)
        if not m:
            return None, None
    owner = m.group(1)
    repo = m.group(2)
    if repo.endswith(".git"):
        repo = repo[:-4]
    return owner, repo


def _gh_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SelfRepair-HealthWorker",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _detect(repo_meta: dict, paths: list[str]) -> list[dict]:
    """Run hygiene detectors against repo metadata + a flat path list."""
    lower = [p.lower() for p in paths]
    issues: list[dict] = []

    def has(predicate) -> bool:
        return any(predicate(p) for p in lower)

    def base(p: str) -> str:
        return p.rsplit("/", 1)[-1]

    has_readme = has(lambda p: base(p).startswith("readme"))
    has_license_file = has(lambda p: base(p).startswith("license") or base(p).startswith("copying"))
    has_ci = has(lambda p: p.startswith(".github/workflows/") and (p.endswith(".yml") or p.endswith(".yaml")))
    has_tests = has(lambda p: "test" in base(p) or p.startswith("tests/") or "/tests/" in p)
    has_contributing = has(lambda p: base(p).startswith("contributing"))
    has_security = has(lambda p: base(p).startswith("security"))
    has_python = has(lambda p: p.endswith(".py"))
    has_pyproject = has(lambda p: base(p) in ("pyproject.toml", "setup.py", "setup.cfg"))
    license_meta = repo_meta.get("license")

    if not has_readme:
        issues.append({
            "id": "missing-readme",
            "severity": "medium",
            "description": "No README file found at the repository root.",
            "recommended_action": "Add a README.md describing the project, setup and usage.",
        })
    if not license_meta and not has_license_file:
        issues.append({
            "id": "missing-license",
            "severity": "medium",
            "description": "No license detected (no LICENSE file and no GitHub license metadata).",
            "recommended_action": "Add a LICENSE file (e.g. Apache-2.0 or MIT) to clarify usage rights.",
        })
    if not has_ci:
        issues.append({
            "id": "missing-ci-workflow",
            "severity": "high",
            "description": "No CI workflow under .github/workflows/.",
            "recommended_action": "Add a CI workflow that runs tests/linters on push and PR.",
        })
    if not has_tests:
        issues.append({
            "id": "missing-tests",
            "severity": "high",
            "description": "No test files or tests directory detected.",
            "recommended_action": "Add automated tests to guard against regressions.",
        })
    if not has_contributing:
        issues.append({
            "id": "missing-contributing",
            "severity": "low",
            "description": "No CONTRIBUTING guide found.",
            "recommended_action": "Add a CONTRIBUTING.md to onboard contributors.",
        })
    if not has_security:
        issues.append({
            "id": "missing-security-policy",
            "severity": "low",
            "description": "No SECURITY policy found.",
            "recommended_action": "Add a SECURITY.md describing how to report vulnerabilities.",
        })
    if has_python and not has_pyproject:
        issues.append({
            "id": "missing-pyproject",
            "severity": "medium",
            "description": "Python sources present but no pyproject.toml/setup.py packaging file.",
            "recommended_action": "Add a pyproject.toml to declare dependencies and build metadata.",
        })

    archived = bool(repo_meta.get("archived"))
    stale = False
    pushed_at = repo_meta.get("pushed_at")
    if pushed_at:
        try:
            dt = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
            stale = (datetime.now(timezone.utc) - dt) > timedelta(days=_STALE_DAYS)
        except Exception:
            stale = False
    if archived or stale:
        issues.append({
            "id": "archived-or-stale",
            "severity": "low",
            "description": (
                "Repository is archived." if archived
                else f"No pushes in over {_STALE_DAYS} days (stale)."
            ),
            "recommended_action": "Confirm the repo is still maintained or mark it as deprecated.",
        })

    return issues


def _score(issues: list[dict]) -> int:
    penalty = sum(_WEIGHTS.get(i.get("severity", "low"), 5) for i in issues)
    return max(0, min(100, 100 - penalty))


def analyze_repo(repo_url: str, branch: str = "main", timeout: float = 20.0) -> dict:
    """Analyze a repo via the GitHub API. Returns a report dict.

    On unavailability (network/404/rate-limit) returns a graceful report with
    ``health_score=None`` and an ``unavailable`` note rather than raising.
    """
    owner, repo = parse_owner_repo(repo_url)
    checked_at = _iso(datetime.now(timezone.utc))
    base_report = {
        "repo_url": repo_url,
        "owner": owner,
        "repo": repo,
        "branch": branch,
        "health_score": None,
        "issues": [],
        "file_count": 0,
        "checked_at": checked_at,
        "source": "github-api",
    }
    if not owner or not repo:
        base_report["note"] = "analysis-unavailable: could not parse owner/repo from URL."
        base_report["unavailable"] = True
        return base_report

    timeouts = httpx.Timeout(timeout, connect=min(timeout, 10.0))
    try:
        with httpx.Client(headers=_gh_headers(), timeout=timeouts, follow_redirects=True) as client:
            r = client.get(f"{GITHUB_API}/repos/{owner}/{repo}")
            if r.status_code == 404:
                base_report["note"] = "analysis-unavailable: repository not found (404)."
                base_report["unavailable"] = True
                return base_report
            if r.status_code in (401, 403):
                base_report["note"] = (
                    "analysis-unavailable: access denied or rate-limited by GitHub "
                    f"({r.status_code})."
                )
                base_report["unavailable"] = True
                return base_report
            r.raise_for_status()
            meta = r.json()
            use_branch = branch or meta.get("default_branch") or "main"
            base_report["branch"] = use_branch
            base_report["description"] = meta.get("description")
            base_report["default_branch"] = meta.get("default_branch")

            # File tree (recursive). Fall back to top-level contents listing.
            paths: list[str] = []
            tr = client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{use_branch}",
                params={"recursive": "1"},
            )
            if tr.status_code == 200:
                tree = tr.json().get("tree", [])
                paths = [n.get("path", "") for n in tree if n.get("type") == "blob"]
            else:
                cr = client.get(f"{GITHUB_API}/repos/{owner}/{repo}/contents")
                if cr.status_code == 200 and isinstance(cr.json(), list):
                    paths = [n.get("path", "") for n in cr.json()]

            issues = _detect(meta, paths)
            base_report.update({
                "health_score": _score(issues),
                "issues": issues,
                "file_count": len(paths),
                "archived": bool(meta.get("archived")),
                "pushed_at": meta.get("pushed_at"),
                "license": (meta.get("license") or {}).get("spdx_id") if meta.get("license") else None,
            })
            return base_report
    except httpx.HTTPError as exc:
        base_report["note"] = f"analysis-unavailable: network error ({type(exc).__name__})."
        base_report["unavailable"] = True
        return base_report
    except Exception as exc:  # pragma: no cover - defensive
        base_report["note"] = f"analysis-unavailable: {type(exc).__name__}."
        base_report["unavailable"] = True
        return base_report


# Map detected issue ids -> the file(s) GitPilot is allowed to touch when
# proposing a fix. Empty mapping (e.g. archived-or-stale) means "no patch".
_ISSUE_PATHS = {
    "missing-readme": ["README.md"],
    "missing-license": ["LICENSE"],
    "missing-ci-workflow": [".github/workflows/**"],
    "missing-tests": ["tests/**"],
    "missing-contributing": ["CONTRIBUTING.md"],
    "missing-security-policy": ["SECURITY.md"],
    "missing-pyproject": ["pyproject.toml"],
}
_DEFAULT_FORBIDDEN = [".env", "secrets/**", "**/*token*", "**/*secret*"]


def _gitpilot_patch_preview(
    repo_url: str, branch: str, issues: list[dict], task_id: str, client_id: str
) -> dict | None:
    """Ask the configured GitPilot service for a DRY-RUN patch preview.

    Returns a compact dict to attach to the report, or None when GitPilot is
    not configured. Degrades gracefully (never raises) if GitPilot is
    unreachable. SelfRepair never writes code itself — this delegates to
    GitPilot, the default coder. No HF_TOKEN is used.
    """
    base = (os.environ.get("GITPILOT_URL") or "").rstrip("/")
    if not base:
        return None  # not wired — health-only report (as before)

    allowed: list[str] = []
    for iss in issues:
        for p in _ISSUE_PATHS.get(iss.get("id", ""), []):
            if p not in allowed:
                allowed.append(p)
    if not allowed:
        return {"status": "skipped", "note": "No fixable paths for the detected issues."}

    plan = {
        "client_id": client_id or "selfrepair",
        "workspace_id": "default",
        "task_id": task_id,
        "repo_url": repo_url,
        "branch": branch or "main",
        "mode": "dry_run",
        "issues": issues,
        "allowed_paths": allowed,
        "forbidden_paths": _DEFAULT_FORBIDDEN,
        "coder": {"provider": "gitpilot", "model": "code-coder"},
        "sandbox": {"provider": "matrixlab", "profile": "python-repair", "required": False},
    }
    headers = {"Content-Type": "application/json"}
    token = os.environ.get("GITPILOT_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    # Retry transient responses (429 rate-limit / 502/503/504) with backoff —
    # Space-to-Space calls can be briefly throttled.
    import time as _time

    last_status: int | None = None
    try:
        with httpx.Client(timeout=httpx.Timeout(45.0, connect=10.0)) as client:
            for attempt in range(3):
                r = client.post(f"{base}/repair", json=plan, headers=headers)
                last_status = r.status_code
                if r.status_code in (429, 502, 503, 504) and attempt < 2:
                    _time.sleep(2 * (attempt + 1))
                    continue
                break
        if last_status is not None and last_status >= 400:
            return {"status": "unavailable", "note": f"GitPilot returned HTTP {last_status}."}
        data = r.json()
        return {
            "status": data.get("status", "ok"),
            "patch_preview": data.get("patch_preview", ""),
            "changed_files": data.get("changed_files", []),
            "review": data.get("review", ""),
            "risk_level": data.get("risk_level", "low"),
            "sandbox_result": data.get("sandbox_result"),
            "pr_url": data.get("pr_url"),
            "coder": "gitpilot",
        }
    except Exception as exc:  # pragma: no cover - depends on runtime egress
        return {"status": "unavailable", "note": f"GitPilot unreachable ({type(exc).__name__})."}


def _run_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.query(Job).filter_by(id=job_id).first()
        if not job:
            return
        job.status = "running"
        db.commit()
        msg = db.query(Message).filter_by(id=job.message_id).first() if job.message_id else None
        if msg:
            msg.status = "running"
            db.commit()

        report = analyze_repo(job.repo_url, job.branch or "main")
        unavailable = bool(report.get("unavailable"))

        # Delegate to GitPilot (the default coder) for a dry-run patch preview
        # when a GitPilot service is configured and there are issues to fix.
        # Attaches to the report; degrades gracefully when GitPilot is absent.
        if not unavailable and report.get("issues"):
            repair = _gitpilot_patch_preview(
                report.get("repo_url") or job.repo_url,
                report.get("branch") or job.branch or "main",
                report.get("issues", []),
                job_id,
                (msg.client_id if msg else "selfrepair"),
            )
            if repair is not None:
                report["repair"] = repair

        job.report_json = json.dumps(report, default=str)
        job.health_score = report.get("health_score")
        job.finished_at = datetime.now(timezone.utc)
        # Graceful degradation: a graceful "unavailable" report still completes
        # as "done" (with a note) so the operator sees the outcome.
        job.status = "done"
        if unavailable:
            job.error = report.get("note")
        db.commit()

        if msg:
            msg.status = job.status
            db.commit()

        owner_repo = "/".join(p for p in (report.get("owner"), report.get("repo")) if p) or job.repo_url
        source = msg.client_id if msg else "system"
        if unavailable:
            notif = Notification(
                source=source,
                kind="action_needed",
                title=f"Health check unavailable · {owner_repo}",
                body=report.get("note"),
                link=job.id,
            )
        else:
            score = report.get("health_score")
            n_issues = len(report.get("issues", []))
            body = f"{n_issues} issue(s) found." if n_issues else "No issues found."
            repair = report.get("repair") or {}
            if repair.get("status") in ("ok", "needs_approval") and repair.get("patch_preview"):
                body += " GitPilot proposed a dry-run patch."
            notif = Notification(
                source=source,
                kind="report_ready",
                title=f"Report ready · {owner_repo} · health {score}",
                body=body,
                link=job.id,
            )
        db.add(notif)
        db.commit()
    except Exception as exc:
        logger.exception("Health job %s failed: %s", job_id, exc)
        try:
            job = db.query(Job).filter_by(id=job_id).first()
            if job:
                job.status = "failed"
                job.error = str(exc)[:500]
                job.finished_at = datetime.now(timezone.utc)
                if job.message_id:
                    m = db.query(Message).filter_by(id=job.message_id).first()
                    if m:
                        m.status = "failed"
                db.add(Notification(
                    source="system",
                    kind="action_needed",
                    title="Health check failed",
                    body=str(exc)[:300],
                    link=job_id,
                ))
                db.commit()
        except Exception:
            logger.exception("Failed to record failure for job %s", job_id)
    finally:
        db.close()


def start_health_job(job_id: str) -> None:
    """Kick off the health worker for ``job_id`` in a daemon thread."""
    thread = threading.Thread(target=_run_job, args=(job_id,), daemon=True)
    thread.start()
