"""RepoGuardian Enterprise Web UI - FastAPI Application."""
from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .database import (
    AuditLog,
    RepoReport,
    ScanRun,
    SessionLocal,
    User,
    init_db,
)
from .scanner import get_scan_status, start_scan
from .security import (
    SECRET_KEY,
    authenticate_user,
    create_user,
    hash_password,
    verify_password,
)

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown."""
    init_db()
    _ensure_admin_user()
    logger.info("RepoGuardian Web UI started")
    yield
    logger.info("RepoGuardian Web UI shutting down")


def _ensure_admin_user():
    """Create default admin user if no users exist."""
    db = SessionLocal()
    try:
        count = db.query(User).count()
        if count == 0:
            admin_pass = os.environ.get("ADMIN_PASSWORD", "guardian2024")
            create_user(
                username="admin",
                email="admin@repoguardian.local",
                password=admin_pass,
                role="admin",
            )
            logger.info("Default admin user created (username: admin)")
    finally:
        db.close()


app = FastAPI(
    title="RepoGuardian",
    description="Enterprise Repository Health & Governance Platform",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="rg_session",
    max_age=86400,  # 24 hours
    same_site="none",  # Required: HF Spaces embeds app in iframe from huggingface.co
    https_only=True,   # Required when SameSite=None
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


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
    return {"status": "ok", "service": "repoguardian-web", "version": "2.0.0"}


# ---------------------------------------------------------------------------
# Public routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = _get_user(request)
    if user:
        return RedirectResponse("/dashboard", status_code=302)
    return _render(request, "home.html")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    user = _get_user(request)
    if user:
        return RedirectResponse("/dashboard", status_code=302)
    return _render(request, "login.html", {"error": None})


@app.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    user = authenticate_user(username, password)
    if not user:
        return _render(request, "login.html", {"error": "Invalid credentials"}, status_code=401)
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["role"] = user.role

    # Audit log
    db = SessionLocal()
    try:
        db.add(AuditLog(user_id=user.id, action="login", ip_address=request.client.host if request.client else None))
        db.commit()
    finally:
        db.close()

    return RedirectResponse("/dashboard", status_code=302)


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    user = _get_user(request)
    if user:
        return RedirectResponse("/dashboard", status_code=302)
    return _render(request, "register.html", {"error": None})


@app.post("/register", response_class=HTMLResponse)
async def register_submit(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
):
    if password != password_confirm:
        return _render(request, "register.html", {"error": "Passwords do not match"})
    if len(password) < 8:
        return _render(request, "register.html", {"error": "Password must be at least 8 characters"})

    db = SessionLocal()
    try:
        if db.query(User).filter((User.email == email) | (User.username == username)).first():
            return _render(request, "register.html", {"error": "Username or email already taken"})
    finally:
        db.close()

    user = create_user(username=username, email=email, password=password)
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["role"] = user.role
    return RedirectResponse("/dashboard", status_code=302)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


# ---------------------------------------------------------------------------
# Authenticated routes
# ---------------------------------------------------------------------------

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = _require_user(request)
    db = SessionLocal()
    try:
        scans = (
            db.query(ScanRun)
            .filter_by(user_id=user.id)
            .order_by(ScanRun.started_at.desc())
            .limit(10)
            .all()
        )
        latest = scans[0] if scans else None
        total_scans = db.query(ScanRun).filter_by(user_id=user.id).count()
        stats = {
            "total_repos": latest.total_repos if latest else 0,
            "healthy": latest.healthy if latest else 0,
            "degraded": latest.degraded if latest else 0,
            "down": latest.down if latest else 0,
            "repaired": latest.repaired if latest else 0,
            "total_scans": total_scans,
        }
        return _render(request, "dashboard.html", {"user": user, "scans": scans, "stats": stats})
    finally:
        db.close()


@app.get("/scan/{scan_id}", response_class=HTMLResponse)
async def scan_detail(request: Request, scan_id: str):
    user = _require_user(request)
    db = SessionLocal()
    try:
        scan = db.query(ScanRun).filter_by(id=scan_id, user_id=user.id).first()
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
        reports = (
            db.query(RepoReport)
            .filter_by(scan_id=scan_id)
            .order_by(RepoReport.status.desc(), RepoReport.repo_name)
            .all()
        )
        return _render(request, "scan_detail.html", {"user": user, "scan": scan, "reports": reports})
    finally:
        db.close()


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    user = _require_user(request)
    return _render(request, "settings.html", {"user": user, "success": None, "error": None})


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
    user = _require_user(request)
    if user.role != "admin":
        raise HTTPException(403, "Admin access required")
    db = SessionLocal()
    try:
        logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(100).all()
        return _render(request, "audit.html", {"user": user, "logs": logs})
    finally:
        db.close()


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
