"""SelfRepair Review — a single-process review bot for a Hugging Face Space.

The full SelfRepair server runs the reviewer behind Postgres, Redis and an Arq
worker. This app is the development and test edition: one process, an
in-memory store, webhooks handled in the background. It reviews pull requests
the way hosted AI reviewers do (status comment, "💡 SelfRepair Review", P0-P3
inline suggestions) and answers `@selfrepair review` / `@selfrepair fix`.

Run:  uvicorn selfrepair.reviewer.space_app:app --port 7860

Environment
-----------
GITHUB_APP_ID, GITHUB_APP_PRIVATE_KEY, GITHUB_WEBHOOK_SECRET
    The GitHub App. Create it from `/setup?token=<SELFREPAIR_SETUP_TOKEN>`.
SELFREPAIR_SETUP_TOKEN
    Required to open `/setup`. Without it the setup page is disabled.
SELFREPAIR_ALLOWED_OWNERS
    Comma-separated GitHub owners whose repositories are reviewed. Empty means
    every repository the app is installed on.
SELFREPAIR_REVIEW_LLM_URL, SELFREPAIR_REVIEW_MODEL, SELFREPAIR_REVIEW_LLM_KEY
    The OpenAI-compatible model (OllaBridge Cloud by default). Without them the
    deterministic engine runs and the check says the model review is missing.
SELFREPAIR_REMEDIATION=true, GITPILOT_URL / GITPILOT_TOKEN
    Let `@selfrepair fix` ask GitPilot for a draft pull request.
HF_TOKEN, SPACE_ID, SPACE_HOST
    Set by Hugging Face (SPACE_*) or as a secret (HF_TOKEN). Used only to save
    the GitHub App credentials created by `/setup` as Space secrets.

Nothing secret is ever returned by an HTTP route.
"""
from __future__ import annotations

import asyncio
import hmac
import html
import json
import logging
import os
import re
import secrets
import uuid
from typing import Any

import httpx
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse

from selfrepair.auth.github_app import verify_webhook_signature
from selfrepair.reviewer.credentials import credential_status, first_env, github_app_from_env
from selfrepair.reviewer.schemas import RepoBinding
from selfrepair.reviewer.store import MemoryReviewStore

logger = logging.getLogger("selfrepair.review_space")

ORG_ID = uuid.UUID(os.getenv("SELFREPAIR_SPACE_ORG_ID") or "00000000-0000-0000-0000-00000000c0de")
_EVENTS = {"pull_request", "issue_comment"}

app = FastAPI(title="SelfRepair Review", docs_url=None, redoc_url=None)
store = MemoryReviewStore(repos=[])
_setup_states: dict[str, float] = {}
_tasks: set[asyncio.Task[Any]] = set()
_stats: dict[str, int] = {"deliveries": 0, "reviews": 0, "commands": 0, "ignored": 0, "errors": 0}


def org_defaults() -> dict[str, Any]:
    """Reviewer settings for every repository this Space reviews."""
    model_ready = bool(first_env("SELFREPAIR_REVIEW_LLM_URL", "SELFREPAIR_OLLABRIDGE_URL",
                                 "OLLABRIDGE_BASE_URL") and first_env("SELFREPAIR_REVIEW_MODEL"))
    return {
        "enabled": True,
        "engine": "llm" if model_ready else "deterministic",
        # Pull requests only, like hosted reviewers; any target branch.
        "triggers": {"push": False, "pull_request": True, "merge_request": False},
        "branches": {"include": [], "exclude": []},
        "review": {"style": "codex"},
        # Large pull requests on free providers take minutes; see docs/reviewer/codex-style.md.
        "execution": {"max_runtime_seconds": int(os.getenv("SELFREPAIR_REVIEW_MAX_SECONDS", "1200"))},
        "remediation": {"enabled": os.getenv("SELFREPAIR_REMEDIATION", "").lower() == "true"},
    }


def _owner_allowed(full_name: str) -> bool:
    allowed = {o.strip().lower() for o in os.getenv("SELFREPAIR_ALLOWED_OWNERS", "").split(",") if o.strip()}
    return not allowed or full_name.split("/", 1)[0].lower() in allowed


def bind_repo(payload: dict[str, Any]) -> RepoBinding | None:
    """Register the repository a webhook came from. Only installed repos send webhooks."""
    repo = payload.get("repository") or {}
    full_name = str(repo.get("full_name") or "")
    installation = (payload.get("installation") or {}).get("id")
    if not full_name or not installation or not _owner_allowed(full_name):
        return None
    for existing in store.repos:
        if existing.full_name == full_name:
            return existing
    binding = RepoBinding(
        org_id=ORG_ID,
        repo_id=uuid.uuid5(uuid.NAMESPACE_URL, f"github:{full_name}"),
        provider="github",
        full_name=full_name,
        default_branch=str(repo.get("default_branch") or "main"),
        installation_id=int(installation),
    )
    store.repos.append(binding)
    return binding


def _ctx() -> dict[str, Any]:
    store.org_settings[ORG_ID] = org_defaults()
    ctx: dict[str, Any] = {"review_store": store, "job_try": 1}
    gh = github_app_from_env()
    if gh is not None:
        ctx["github_app"] = gh
    return ctx


async def process(event_type: str, delivery_id: str, payload: dict[str, Any]) -> str:
    """Handle one verified delivery. Never raises; outcomes are counted."""
    from selfrepair.reviewer.commands import handle_github_comment
    from selfrepair.reviewer.dispatcher import dispatch_github_review_event

    try:
        if bind_repo(payload) is None:
            _stats["ignored"] += 1
            return "ignored"
        ctx = _ctx()
        if event_type == "issue_comment":
            outcome = await handle_github_comment(ctx, delivery_id, payload) or "ignored"
            _stats["commands" if outcome != "ignored" else "ignored"] += 1
        else:
            outcome = await dispatch_github_review_event(
                ctx=ctx, event_type=event_type, delivery_id=delivery_id, payload=payload)
            _stats["reviews" if outcome in {"reviewed", "incomplete"} else "ignored"] += 1
        logger.info("delivery=%s event=%s outcome=%s", delivery_id, event_type, outcome)
        return outcome
    except Exception as exc:  # noqa: BLE001 - logged by type only
        _stats["errors"] += 1
        logger.warning("delivery=%s failed: %s", delivery_id, type(exc).__name__)
        return "error"


@app.post("/webhooks/github")
async def github_webhook(
    request: Request,
    background: BackgroundTasks,
    x_github_event: str = Header(default=""),
    x_github_delivery: str = Header(default=""),
    x_hub_signature_256: str | None = Header(default=None),
) -> dict[str, str]:
    body = await request.body()
    secret = first_env("GITHUB_WEBHOOK_SECRET", "SELFREPAIR_GITHUB_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(status_code=503, detail="webhook secret not configured")
    if not verify_webhook_signature(secret=secret, payload=body, header=x_hub_signature_256):
        raise HTTPException(status_code=401, detail="bad signature")
    _stats["deliveries"] += 1
    if x_github_event == "ping":
        return {"status": "pong"}
    if x_github_event not in _EVENTS:
        return {"status": "ignored"}
    payload = json.loads(body)
    # GitHub expects an answer within 10 seconds; the review runs afterwards.
    background.add_task(process, x_github_event, x_github_delivery, payload)
    return {"status": "accepted", "delivery_id": x_github_delivery}


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    creds = credential_status()
    return {
        "ok": True,
        "github_app": creds["github_app"],
        "webhook_secret": bool(first_env("GITHUB_WEBHOOK_SECRET")),
        "engine": org_defaults()["engine"],
        "remediation": org_defaults()["remediation"]["enabled"],
        "repositories": len(store.repos),
        "stats": dict(_stats),
    }


@app.get("/", response_class=HTMLResponse)
async def home() -> str:
    h = await healthz()
    def row(label: str, ok: bool, note: str) -> str:
        mark = "✅" if ok else "⚪"
        return f"<tr><td>{mark}</td><td>{label}</td><td>{html.escape(note)}</td></tr>"
    rows = "".join([
        row("GitHub App", h["github_app"], "configured" if h["github_app"] else "open /setup with the setup token"),
        row("Webhook secret", h["webhook_secret"], "set" if h["webhook_secret"] else "missing"),
        row("Review model", h["engine"] == "llm", "model review on" if h["engine"] == "llm"
            else "deterministic checks only — set SELFREPAIR_REVIEW_LLM_URL and SELFREPAIR_REVIEW_MODEL"),
        row("@selfrepair fix", h["remediation"], "GitPilot draft PRs on" if h["remediation"] else "off"),
    ])
    stats = " · ".join(f"{k}: {v}" for k, v in h["stats"].items())
    return _page("SelfRepair Review", f"""
<p class=lead>Reviews pull requests and answers <code>@selfrepair review</code> and
<code>@selfrepair fix</code>. Never approves or merges.</p>
<table>{rows}</table>
<p class=muted>Repositories seen: {h['repositories']} · {html.escape(stats)}</p>""")


# ── GitHub App setup (manifest flow) ─────────────────────────────────────────

def _base_url() -> str:
    host = os.getenv("SPACE_HOST") or os.getenv("SELFREPAIR_PUBLIC_HOST") or ""
    return f"https://{host}" if host and not host.startswith("http") else host


def _require_setup_token(token: str) -> None:
    expected = os.getenv("SELFREPAIR_SETUP_TOKEN", "")
    if not expected or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(status_code=404, detail="Not found")


def manifest(base: str) -> dict[str, Any]:
    return {
        "name": os.getenv("SELFREPAIR_APP_NAME") or "SelfRepair Review Dev",
        "url": base,
        "hook_attributes": {"url": f"{base}/webhooks/github", "active": True},
        "redirect_url": f"{base}/setup/callback",
        "public": False,
        "default_permissions": {
            "contents": "read",
            "metadata": "read",
            "pull_requests": "write",
            "issues": "write",
            "checks": "write",
        },
        "default_events": ["pull_request", "issue_comment"],
    }


@app.get("/setup", response_class=HTMLResponse)
async def setup(token: str = "", org: str = "") -> str:
    _require_setup_token(token)
    if org and not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})", org):
        raise HTTPException(status_code=400, detail="invalid organization name")
    if credential_status()["github_app"]:
        return _page("Already set up", "<p>The GitHub App is configured. Install it on a repository "
                     "and open a pull request.</p>")
    base = _base_url()
    if not base:
        raise HTTPException(status_code=500, detail="SPACE_HOST is not set")
    state = secrets.token_urlsafe(24)
    _setup_states[state] = asyncio.get_event_loop().time()
    target = (f"https://github.com/organizations/{org}/settings/apps/new" if org
              else "https://github.com/settings/apps/new")
    data = html.escape(json.dumps(manifest(base)), quote=True)
    return _page("Create the GitHub App", f"""
<p>This creates a private GitHub App that sends pull-request and comment webhooks to
<code>{html.escape(base)}</code>. Its credentials are saved as secrets of this Space and are
never shown.</p>
<form action="{target}?state={state}" method="post">
<input type="hidden" name="manifest" value="{data}">
<button type="submit">Create GitHub App on GitHub</button></form>""")


@app.get("/setup/callback", response_class=HTMLResponse)
async def setup_callback(code: str = "", state: str = "") -> str:
    if not state or _setup_states.pop(state, None) is None or not code:
        raise HTTPException(status_code=400, detail="Setup link expired. Start again from /setup.")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"https://api.github.com/app-manifests/{code}/conversions",
            headers={"Accept": "application/vnd.github+json"})
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="GitHub did not create the app")
    data = response.json()
    values = {
        "GITHUB_APP_ID": str(data["id"]),
        "GITHUB_APP_PRIVATE_KEY": data["pem"],
        "GITHUB_WEBHOOK_SECRET": data["webhook_secret"],
    }
    os.environ.update(values)  # works at once; secrets keep it across restarts
    saved = await save_space_secrets(values)
    slug = html.escape(str(data.get("slug") or ""))
    note = ("Saved as Space secrets." if saved else
            "<b>Not saved as Space secrets</b> (HF_TOKEN or SPACE_ID missing): they last until restart.")
    return _page("GitHub App created", f"""
<p>{note}</p>
<p><a class=button href="https://github.com/apps/{slug}/installations/new">Install it on repositories</a></p>
<p class=muted>Then open a pull request, or comment <code>@selfrepair review</code> on one.</p>""")


async def save_space_secrets(values: dict[str, str]) -> bool:
    space, token = os.getenv("SPACE_ID", ""), os.getenv("HF_TOKEN", "")
    if not space or not token:
        return False
    async with httpx.AsyncClient(timeout=30) as client:
        for key, value in values.items():
            response = await client.post(
                f"https://huggingface.co/api/spaces/{space}/secrets",
                headers={"Authorization": f"Bearer {token}"},
                json={"key": key, "value": value})
            if response.status_code >= 400:
                logger.warning("space secret %s not saved: %s", key, response.status_code)
                return False
    return True


def _page(title: str, body: str) -> str:
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>
:root{{color-scheme:dark}}body{{margin:0;font:15px/1.6 system-ui,-apple-system,Segoe UI,sans-serif;
background:#0b0c10;color:#e8e8ee}}main{{max-width:640px;margin:0 auto;padding:40px 20px}}
h1{{font-size:24px;letter-spacing:-.02em}}.lead{{color:#b9bacb}}.muted{{color:#8a8ba0;font-size:13px}}
table{{width:100%;border-collapse:collapse;margin:20px 0}}td{{padding:10px 8px;border-top:1px solid #23242f}}
code{{background:#181922;padding:2px 6px;border-radius:6px}}
button,.button{{display:inline-block;background:#ff7a3c;color:#120a05;border:0;border-radius:10px;
padding:12px 18px;font-weight:700;text-decoration:none;cursor:pointer;font-size:15px}}
</style></head><body><main><h1>💡 {html.escape(title)}</h1>{body}</main></body></html>"""
