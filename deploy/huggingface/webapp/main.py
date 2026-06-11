"""RepoGuardian Enterprise Web UI - FastAPI Application."""
from __future__ import annotations

import json
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .database import (
    AuditLog,
    Connection,
    ScanRun,
    SessionLocal,
    User,
    init_db,
)
from .api_v1 import router as api_v1_router
from . import auth_service
from .scanner import get_scan_status, start_scan
from .security import (
    SECRET_KEY,
    authenticate_user,
    create_user,
    hash_password,
    verify_password,
)
from . import clients, crypto, email_service, redis_client

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown."""
    init_db()
    _ensure_admin_user()
    _ensure_root()
    _maybe_reset_root_password()
    logger.info("SelfRepair web started")
    yield
    logger.info("RepoGuardian Web UI shutting down")


# Re-exported from auth_service so the two auth surfaces stay in lockstep.
APP_BASE_URL = auth_service.APP_BASE_URL
VERIFY_TTL = auth_service.VERIFY_TTL
RESET_TTL = auth_service.RESET_TTL


def _ensure_admin_user():
    """Create default admin user if no users exist."""
    db = SessionLocal()
    try:
        count = db.query(User).count()
        if count == 0:
            admin_pass = os.environ.get("ADMIN_PASSWORD", "selfrepair2024")
            admin_email = os.environ.get("ADMIN_EMAIL", "admin@selfrepair.local")
            user = create_user(
                username="admin",
                email=admin_email,
                password=admin_pass,
                role="admin",
            )
            # Admin is pre-verified and is the bootstrap root superuser.
            db_user = db.query(User).filter_by(id=user.id).first()
            db_user.email_verified = True
            db_user.is_root = True
            db.commit()
            logger.info("Default root admin created (username: admin)")
    finally:
        db.close()


def _ensure_root():
    """Guarantee exactly one protected root superuser exists.

    On a fresh DB the seeded admin is already root. On an existing DB (e.g. the
    live Neon database created before the root model), promote the ADMIN_EMAIL
    account — else the oldest admin, else the oldest user — to root so there is
    always a single bootstrap superuser who can grant admin to others.
    """
    db = SessionLocal()
    try:
        if db.query(User).filter_by(is_root=True).count() > 0:
            return
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@selfrepair.local")
        target = (
            db.query(User).filter_by(email=admin_email).first()
            or db.query(User).filter_by(role="admin").order_by(User.created_at.asc()).first()
            or db.query(User).order_by(User.created_at.asc()).first()
        )
        if target:
            target.is_root = True
            target.role = "admin"
            target.is_active = True
            target.email_verified = True
            db.commit()
            logger.info("SelfRepair: promoted %s to root superuser.", target.email)
    finally:
        db.close()


def _maybe_reset_root_password():
    """Break-glass: when ADMIN_RESET_PASSWORD=1, reset the root password to
    ADMIN_PASSWORD on startup. For recovering a lost root credential — remove
    the flag once you've signed in. Never logs the password."""
    if os.environ.get("ADMIN_RESET_PASSWORD") != "1":
        return
    new_pw = os.environ.get("ADMIN_PASSWORD")
    if not new_pw:
        return
    db = SessionLocal()
    try:
        root = db.query(User).filter_by(is_root=True).first()
        if root:
            root.password_hash = hash_password(new_pw)
            root.is_active = True
            root.email_verified = True
            db.commit()
            logger.warning(
                "SelfRepair: root password reset from ADMIN_PASSWORD (ADMIN_RESET_PASSWORD=1). "
                "Remove ADMIN_RESET_PASSWORD now."
            )
    finally:
        db.close()


app = FastAPI(
    title="SelfRepair",
    description="Generic repository maintenance — plan, delegate, validate, report",
    version="2.0.0",
    lifespan=lifespan,
)

# HF Spaces embeds the app in an iframe from huggingface.co, which requires
# SameSite=None + Secure cookies. For local HTTP testing set
# SELFREPAIR_INSECURE_COOKIES=1 to fall back to SameSite=Lax (non-secure).
_insecure_cookies = os.environ.get("SELFREPAIR_INSECURE_COOKIES") == "1"
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="sr_session",
    max_age=86400,  # 24 hours
    same_site="lax" if _insecure_cookies else "none",
    https_only=not _insecure_cookies,
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# Mount the `/v1` JSON compatibility API consumed by the React SPA.
app.include_router(api_v1_router)

# ---------------------------------------------------------------------------
# SPA (SelfRepair Console) — built React app served at "/".
# ---------------------------------------------------------------------------
SPA_DIR = BASE_DIR / "spa"
SPA_INDEX = SPA_DIR / "index.html"
if (SPA_DIR / "assets").is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=str(SPA_DIR / "assets")),
        name="spa-assets",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _render(request: Request, name: str, ctx: dict | None = None, status_code: int = 200):
    """Render a template with cross-version Starlette compatibility."""
    context = dict(ctx) if ctx else {}
    context["request"] = request
    return templates.TemplateResponse(request=request, name=name, context=context, status_code=status_code)


def _get_user(request: Request) -> User | None:
    """Get current logged-in user from session."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    db = SessionLocal()
    try:
        return db.query(User).filter_by(id=user_id, is_active=True).first()
    finally:
        db.close()


def _require_user(request: Request) -> User:
    """Require authenticated user or redirect to login."""
    user = _get_user(request)
    if not user:
        raise _LoginRedirect()
    return user


class _LoginRedirect(Exception):
    pass


@app.exception_handler(_LoginRedirect)
async def _login_redirect_handler(request: Request, exc: _LoginRedirect):
    return RedirectResponse("/login", status_code=302)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    from .database import engine

    return {
        "status": "ok",
        "service": "selfrepair-web",
        "version": "2.0.0",
        "backends": {
            "db": engine.dialect.name,            # "postgresql" when Neon is reachable
            "redis": redis_client.configured(),   # Upstash configured?
            "email": email_service.configured(),  # Mailtrap configured?
        },
    }


# ---------------------------------------------------------------------------
# Connections (OllaBridge / GitPilot / MatrixLab)
# ---------------------------------------------------------------------------

def _load_connections(user_id: str) -> dict[str, Connection]:
    """Return the user's connections keyed by provider, creating defaults."""
    db = SessionLocal()
    try:
        existing = {c.provider: c for c in db.query(Connection).filter_by(user_id=user_id).all()}
        created = False
        for provider in clients.PROVIDERS:
            if provider not in existing:
                conn = Connection(
                    user_id=user_id,
                    provider=provider,
                    base_url=clients.DEFAULTS[provider],
                    status="unknown",
                )
                db.add(conn)
                created = True
        if created:
            db.commit()
            existing = {c.provider: c for c in db.query(Connection).filter_by(user_id=user_id).all()}
        # detach
        for c in existing.values():
            db.refresh(c)
            db.expunge(c)
        return existing
    finally:
        db.close()


def _connection_view(conn: Connection) -> dict:
    secret = crypto.decrypt(conn.api_key_enc or "")
    return {
        "provider": conn.provider,
        "label": clients.PROVIDER_LABELS.get(conn.provider, conn.provider),
        "base_url": conn.base_url or clients.DEFAULTS.get(conn.provider, ""),
        "has_secret": bool(secret),
        "masked_secret": crypto.mask(secret),
        "status": conn.status or "unknown",
        "detail": conn.detail or "",
        "last_checked_at": conn.last_checked_at.isoformat() if conn.last_checked_at else None,
        "default_url": clients.DEFAULTS.get(conn.provider, ""),
    }


@app.get("/connections", response_class=HTMLResponse)
async def connections_page(request: Request):
    # The React console owns this screen now; serve the SPA so the dark
    # Connections surface (GET/POST /v1/connections) renders instead of the
    # retired green Jinja page.
    return _spa_index()


@app.post("/connections/{provider}")
async def connections_save(
    request: Request,
    provider: str,
    base_url: str = Form(""),
    api_key: str = Form(""),
):
    user = _require_user(request)
    if provider not in clients.PROVIDERS:
        raise HTTPException(404, "Unknown provider")
    _load_connections(user.id)  # ensure rows exist
    db = SessionLocal()
    try:
        conn = db.query(Connection).filter_by(user_id=user.id, provider=provider).first()
        conn.base_url = (base_url or clients.DEFAULTS[provider]).strip()
        if api_key.strip():
            conn.api_key_enc = crypto.encrypt(api_key.strip())
        # Run a live probe right away.
        secret = crypto.decrypt(conn.api_key_enc or "")
        result = clients.test_provider(provider, conn.base_url, secret)
        conn.status = result["status"]
        conn.detail = result["detail"]
        conn.last_checked_at = datetime.now(timezone.utc)
        db.add(AuditLog(user_id=user.id, action=f"connection_saved:{provider}", details=result["status"]))
        db.commit()
        return JSONResponse({"ok": True, **result})
    finally:
        db.close()


@app.post("/connections/{provider}/test")
async def connections_test(request: Request, provider: str):
    user = _require_user(request)
    if provider not in clients.PROVIDERS:
        raise HTTPException(404, "Unknown provider")
    conns = _load_connections(user.id)
    conn = conns[provider]
    secret = crypto.decrypt(conn.api_key_enc or "")
    result = clients.test_provider(provider, conn.base_url or clients.DEFAULTS[provider], secret)
    db = SessionLocal()
    try:
        row = db.query(Connection).filter_by(user_id=user.id, provider=provider).first()
        row.status = result["status"]
        row.detail = result["detail"]
        row.last_checked_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()
    return JSONResponse(result)


@app.post("/api/pipeline/verify")
async def api_pipeline_verify(request: Request):
    """Probe all three providers and return a combined status report."""
    user = _require_user(request)
    conns = _load_connections(user.id)
    out: dict[str, dict] = {}
    db = SessionLocal()
    try:
        for provider in clients.PROVIDERS:
            conn = conns[provider]
            secret = crypto.decrypt(conn.api_key_enc or "")
            result = clients.test_provider(provider, conn.base_url or clients.DEFAULTS[provider], secret)
            out[provider] = result
            row = db.query(Connection).filter_by(user_id=user.id, provider=provider).first()
            row.status = result["status"]
            row.detail = result["detail"]
            row.last_checked_at = datetime.now(timezone.utc)
        db.add(AuditLog(user_id=user.id, action="pipeline_verify"))
        db.commit()
    finally:
        db.close()
    return JSONResponse({"providers": out})


@app.post("/api/ollabridge/sample")
async def api_ollabridge_sample(request: Request, prompt: str = Form("Write a minimal pytest health check.")):
    user = _require_user(request)
    conns = _load_connections(user.id)
    conn = conns["ollabridge"]
    secret = crypto.decrypt(conn.api_key_enc or "")
    result = clients.ollabridge_sample_completion(conn.base_url or clients.DEFAULTS["ollabridge"], secret, prompt)
    return JSONResponse(result)


# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------

# index.html must never be cached: it points at hash-named asset bundles that
# change every deploy. A stale cached index.html references deleted hashes and
# 404s. Hashed assets under /assets are immutable and may cache freely.
_NO_STORE = {"Cache-Control": "no-store, max-age=0, must-revalidate"}


def _spa_index() -> FileResponse:
    return FileResponse(str(SPA_INDEX), headers=_NO_STORE)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    # The React SPA (SelfRepair Console) owns the root. Fall back to the
    # server-rendered marketing/home page only if the SPA build is absent.
    if SPA_INDEX.is_file():
        return _spa_index()
    user = _get_user(request)
    if user:
        return RedirectResponse("/dashboard", status_code=302)
    return _render(request, "home.html")


@app.get("/favicon.svg", include_in_schema=False)
async def spa_favicon():
    fav = SPA_DIR / "favicon.svg"
    if fav.is_file():
        return FileResponse(str(fav), media_type="image/svg+xml")
    raise HTTPException(status_code=404)


# Validation primitives + flow helpers live in auth_service so the JSON
# `/v1/auth/*` endpoints and these Jinja handlers share one implementation.
_EMAIL_RE = auth_service.EMAIL_RE
_USERNAME_RE = auth_service.USERNAME_RE
_password_problem = auth_service.password_problem
_audit = auth_service.audit
_issue_verification = auth_service.issue_verification


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _start_session(request: Request, user) -> None:
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["role"] = user.role


# ---- Login ----

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    # Retired green page — the React console's AuthGate renders the sign-in
    # card. Old links/bookmarks land in the SPA.
    return _spa_index()


@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    ip = _client_ip(request)
    allowed, _ = redis_client.rate_limit("login", ip, limit=10, window_seconds=300)
    if not allowed:
        return _render(request, "login.html", {"error": "Too many attempts. Try again in a few minutes."}, status_code=429)

    user = authenticate_user(username, password)
    if not user:
        _audit("login_failed", ip=ip, details=username[:120])
        return _render(request, "login.html", {"error": "Invalid credentials"}, status_code=401)

    if not user.email_verified and user.role != "admin":
        return _render(
            request,
            "login.html",
            {"error": "Please verify your email before signing in.", "unverified_email": user.email},
            status_code=403,
        )

    _start_session(request, user)
    _audit("login", user_id=user.id, ip=ip)
    return RedirectResponse("/dashboard", status_code=302)


# ---- Registration ----

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    # Retired green page — the React console's AuthGate renders Register.
    return _spa_index()


@app.post("/register", response_class=HTMLResponse)
async def register_submit(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
):
    ip = _client_ip(request)
    allowed, _ = redis_client.rate_limit("register", ip, limit=5, window_seconds=3600)
    if not allowed:
        return _render(request, "register.html", {"error": "Too many sign-ups from this network. Try again later."}, status_code=429)

    username = username.strip()
    email = email.strip().lower()
    if not _USERNAME_RE.match(username):
        return _render(request, "register.html", {"error": "Username must be 3–32 chars (letters, numbers, . _ -)."})
    if not _EMAIL_RE.match(email):
        return _render(request, "register.html", {"error": "Enter a valid email address."})
    if password != password_confirm:
        return _render(request, "register.html", {"error": "Passwords do not match."})
    problem = _password_problem(password)
    if problem:
        return _render(request, "register.html", {"error": problem})

    db = SessionLocal()
    try:
        if db.query(User).filter((User.email == email) | (User.username == username)).first():
            return _render(request, "register.html", {"error": "Username or email already taken."})
    finally:
        db.close()

    user = create_user(username=username, email=email, password=password)
    link = _issue_verification(user)
    _audit("register", user_id=user.id, ip=ip, details=email)
    ctx = {
        "email": email,
        "demo_link": link if email_service.demo_links_enabled() else None,
        "delivery": email_service.configured(),
    }
    return _render(request, "verify_sent.html", ctx)


# ---- Email verification ----

@app.get("/verify", response_class=HTMLResponse)
async def verify_email(request: Request):
    # Serve the SPA; VerifyEmail reads ?token= from the URL and POSTs to
    # /v1/auth/verify. (Old emails link here with ?token=.)
    return _spa_index()


@app.post("/resend-verification", response_class=HTMLResponse)
async def resend_verification(request: Request, email: str = Form(...)):
    ip = _client_ip(request)
    email = email.strip().lower()
    allowed, _ = redis_client.rate_limit("resend", ip, limit=5, window_seconds=3600)
    if allowed:
        db = SessionLocal()
        try:
            user = db.query(User).filter_by(email=email).first()
            if user and not user.email_verified:
                db.expunge(user)
                _issue_verification(user)
        finally:
            db.close()
    # Neutral response — don't reveal whether the email exists.
    return _render(request, "verify_sent.html", {"email": email, "demo_link": None, "delivery": email_service.configured(), "resent": True})


# ---- Password reset ----

@app.get("/forgot-password", response_class=HTMLResponse)
async def forgot_page(request: Request):
    # Retired green page — the React console's AuthGate renders ForgotPassword.
    return _spa_index()


@app.post("/forgot-password", response_class=HTMLResponse)
async def forgot_submit(request: Request, email: str = Form(...)):
    ip = _client_ip(request)
    email = email.strip().lower()
    allowed, _ = redis_client.rate_limit("forgot", ip, limit=5, window_seconds=3600)
    if allowed:
        db = SessionLocal()
        try:
            user = db.query(User).filter_by(email=email).first()
            if user:
                token = redis_client.put_token("reset", user.id, RESET_TTL)
                link = f"{APP_BASE_URL}/reset-password?token={token}"
                email_service.send_reset_email(user.email, link)
                _audit("password_reset_requested", user_id=user.id, ip=ip)
        finally:
            db.close()
    # Reset links are delivered by email only — never surfaced in the UI,
    # even in demo mode, to avoid an account-takeover vector.
    return _render(request, "forgot_password.html", {"sent": True, "error": None, "demo_link": None})


@app.get("/reset-password", response_class=HTMLResponse)
async def reset_page(request: Request):
    # Serve the SPA; ResetPassword reads ?token= from the URL and POSTs to
    # /v1/auth/reset-password. (Reset emails link here with ?token=.)
    return _spa_index()


@app.post("/reset-password", response_class=HTMLResponse)
async def reset_submit(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
):
    if password != password_confirm:
        return _render(request, "reset_password.html", {"token": token, "error": "Passwords do not match."})
    problem = _password_problem(password)
    if problem:
        return _render(request, "reset_password.html", {"token": token, "error": problem})

    user_id = redis_client.pop_token("reset", token)
    if not user_id:
        return _render(request, "reset_password.html", {"token": "", "error": "This reset link is invalid or has expired."})

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(id=user_id).first()
        if not user:
            return _render(request, "reset_password.html", {"token": "", "error": "Account not found."})
        user.password_hash = hash_password(password)
        user.email_verified = True  # proves email ownership
        db.add(AuditLog(user_id=user.id, action="password_reset"))
        db.commit()
    finally:
        db.close()
    return RedirectResponse("/login?reset=1", status_code=302)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


# ---------------------------------------------------------------------------
# Authenticated routes
# ---------------------------------------------------------------------------

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    # Retired green page — the React console (Overview) owns the dashboard.
    return _spa_index()


@app.get("/scan/{scan_id}", response_class=HTMLResponse)
async def scan_detail(request: Request, scan_id: str):
    # Retired green page — the React console owns scan/job detail views.
    return _spa_index()


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    # Retired green page — the React console (Settings) owns this screen.
    return _spa_index()


@app.post("/settings", response_class=HTMLResponse)
async def settings_update(
    request: Request,
    display_name: str = Form(""),
    github_token: str = Form(""),
    github_org: str = Form(""),
    github_user: str = Form(""),
    gitlab_token: str = Form(""),
    hf_token: str = Form(""),
    hf_namespace: str = Form(""),
    current_password: str = Form(""),
    new_password: str = Form(""),
):
    user = _require_user(request)
    db = SessionLocal()
    try:
        db_user = db.query(User).filter_by(id=user.id).first()
        if not db_user:
            raise HTTPException(404)

        if display_name:
            db_user.display_name = display_name
        if github_token:
            db_user.github_token = github_token
        if gitlab_token:
            db_user.gitlab_token = gitlab_token
        if hf_token:
            db_user.hf_token = hf_token

        # Password change
        if new_password:
            if not current_password or not verify_password(current_password, db_user.password_hash):
                return _render(request, "settings.html", {"user": db_user, "success": None, "error": "Current password is incorrect"})
            if len(new_password) < 8:
                return _render(request, "settings.html", {"user": db_user, "success": None, "error": "New password must be at least 8 characters"})
            db_user.password_hash = hash_password(new_password)

        db.add(AuditLog(user_id=user.id, action="settings_updated"))
        db.commit()
        db.refresh(db_user)

        return _render(request, "settings.html", {"user": db_user, "success": "Settings saved", "error": None})
    finally:
        db.close()


@app.get("/audit", response_class=HTMLResponse)
async def audit_log(request: Request):
    # Retired green page — the React console (Audit log) owns this screen.
    return _spa_index()


# ---------------------------------------------------------------------------
# API endpoints (JSON)
# ---------------------------------------------------------------------------

@app.post("/api/scan/start")
async def api_start_scan(request: Request):
    user = _require_user(request)
    db = SessionLocal()
    try:
        db_user = db.query(User).filter_by(id=user.id).first()
        settings_override = {
            "github_token": db_user.github_token or os.environ.get("GITHUB_TOKEN", ""),
            "github_org": os.environ.get("GITHUB_ORG", ""),
            "github_user": os.environ.get("GITHUB_USER", ""),
            "gitlab_token": db_user.gitlab_token or "",
            "hf_token": db_user.hf_token or os.environ.get("HF_TOKEN", ""),
            "hf_namespace": os.environ.get("HF_NAMESPACE", ""),
        }
    finally:
        db.close()

    scan_id = start_scan(user.id, settings_override)
    return JSONResponse({"scan_id": scan_id, "status": "running"})


@app.get("/api/scan/{scan_id}/status")
async def api_scan_status(request: Request, scan_id: str):
    _require_user(request)
    status = get_scan_status(scan_id)
    if not status:
        raise HTTPException(404, "Scan not found")
    return JSONResponse(status)


@app.get("/api/stats")
async def api_stats(request: Request):
    user = _require_user(request)
    db = SessionLocal()
    try:
        total_scans = db.query(ScanRun).filter_by(user_id=user.id).count()
        latest = (
            db.query(ScanRun)
            .filter_by(user_id=user.id, status="completed")
            .order_by(ScanRun.finished_at.desc())
            .first()
        )
        return JSONResponse({
            "total_scans": total_scans,
            "latest_scan": {
                "total_repos": latest.total_repos,
                "healthy": latest.healthy,
                "degraded": latest.degraded,
                "down": latest.down,
                "repaired": latest.repaired,
            } if latest else None,
        })
    finally:
        db.close()


# ---------------------------------------------------------------------------
# SPA catch-all (registered LAST so it never shadows API / server routes).
# Any non-API, non-static GET path falls back to the SPA's index.html so the
# React app can handle its own client-side routing.
# ---------------------------------------------------------------------------

# Prefixes that belong to the backend and must 404 (not return index.html)
# when no concrete route matches them.
_API_PREFIXES = ("v1/", "api/", "static/", "assets/")


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_catch_all(request: Request, full_path: str):
    if not SPA_INDEX.is_file():
        raise HTTPException(status_code=404)
    if any(full_path.startswith(p) for p in _API_PREFIXES):
        raise HTTPException(status_code=404)
    # A real file in the SPA build (e.g. favicon.svg, manifest) — serve it.
    candidate = (SPA_DIR / full_path).resolve()
    try:
        candidate.relative_to(SPA_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=404)
    if candidate.is_file():
        return FileResponse(str(candidate))
    return _spa_index()
