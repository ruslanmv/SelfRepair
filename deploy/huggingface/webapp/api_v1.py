"""`/v1` JSON compatibility API for the SelfRepair Console SPA.

This router adapts the lightweight webapp's real data model (Users,
Connections, ScanRuns, RepoReports, AuditLog) to the request paths and
response *shapes* the React SPA (``frontend/``) expects.

Design rules:
  * Real data where it exists (auth/me, org, dashboard counts,
    integrations, audit).
  * Valid EMPTY collections elsewhere (repos/jobs/findings/repairs/
    policies/issues/schedules) — never fabricated rows.
  * All endpoints except ``/v1/auth/login`` require the existing cookie
    session. Auth failures return 401 so React Query treats them as
    "not logged in" rather than crashing.

The SPA reads list endpoints as ``{items: [...]}`` (some also read
``count`` / ``next_cursor``). The dashboard, me, org and integrations
shapes are derived by inspecting the surfaces that consume them.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from datetime import datetime, timezone

from . import auth_service, clients, crypto, email_service, redis_client
from .database import (
    AuditLog,
    Connection,
    Job,
    Message,
    Notification,
    ScanRun,
    SessionLocal,
    User,
    engine,
)
from .health_worker import parse_owner_repo, start_health_job
from .ingest_auth import resolve_client
from .security import authenticate_user

router = APIRouter(prefix="/v1")


# ---------------------------------------------------------------------------
# Session helpers (mirror main.py, kept local to avoid circular import)
# ---------------------------------------------------------------------------

def _current_user(request: Request) -> User | None:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    db = SessionLocal()
    try:
        return db.query(User).filter_by(id=user_id, is_active=True).first()
    finally:
        db.close()


def _require(request: Request) -> User:
    user = _current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def _require_admin(request: Request) -> User:
    user = _require(request)
    if (user.role or "user") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _start_session(request: Request, user: User) -> None:
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["role"] = user.role


# ---------------------------------------------------------------------------
# Serialisers
# ---------------------------------------------------------------------------

def _org_view(user: User) -> dict[str, Any]:
    name = (user.display_name or "SelfRepair").strip() or "SelfRepair"
    return {"id": "default", "name": name, "plan": "free"}


def _user_view(user: User) -> dict[str, Any]:
    name = user.display_name or user.username
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "display_name": user.display_name,
        "name": name,
        "role": user.role or "user",
        "email_verified": bool(user.email_verified),
    }


def _me_view(user: User) -> dict[str, Any]:
    return {"user": _user_view(user), "org": _org_view(user)}


def _empty_list() -> dict[str, Any]:
    """The canonical empty-collection shape the SPA list surfaces read."""
    return {"items": [], "count": 0, "total": 0, "next_cursor": None}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

async def _read_credentials(request: Request) -> tuple[str, str]:
    """Accept JSON ({email|username, password}) or form-encoded bodies."""
    ctype = request.headers.get("content-type", "")
    identifier = ""
    password = ""
    if "application/json" in ctype:
        try:
            data = await request.json()
        except Exception:
            data = {}
        if isinstance(data, dict):
            identifier = str(data.get("email") or data.get("username") or "")
            password = str(data.get("password") or "")
    else:
        form = await request.form()
        identifier = str(form.get("email") or form.get("username") or "")
        password = str(form.get("password") or "")
    return identifier.strip(), password


@router.post("/auth/login")
async def auth_login(request: Request):
    identifier, password = await _read_credentials(request)
    if not identifier or not password:
        raise HTTPException(status_code=400, detail="Email and password required")

    user = authenticate_user(identifier, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.email_verified and user.role != "admin":
        raise HTTPException(status_code=403, detail="Email not verified")

    _start_session(request, user)
    db = SessionLocal()
    try:
        db.add(AuditLog(user_id=user.id, action="login"))
        db.commit()
    finally:
        db.close()
    return JSONResponse(_me_view(user))


@router.post("/auth/logout")
async def auth_logout(request: Request):
    request.session.clear()
    return Response(status_code=200)


@router.post("/auth/refresh")
async def auth_refresh(request: Request):
    # No server-side refresh token; the session cookie is the source of
    # truth. Return 200 so the SPA's optional refresh call is a no-op.
    return Response(status_code=200)


# ---------------------------------------------------------------------------
# JSON auth flows (register / verify / forgot / reset) — the SPA owns auth.
# These mirror main.py's Jinja handlers EXACTLY via the shared auth_service:
# same validation, rate limits, neutral responses (no account-existence leak),
# email-verification gating, and never surfacing reset links.
# ---------------------------------------------------------------------------

def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _json_body(request: Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        data = {}
    return data if isinstance(data, dict) else {}


@router.post("/auth/register")
async def auth_register(request: Request):
    ip = _client_ip(request)
    allowed, _ = redis_client.rate_limit("register", ip, limit=5, window_seconds=3600)
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many sign-ups from this network. Try again later.")

    body = await _json_body(request)
    username = str(body.get("username") or "")
    email = str(body.get("email") or "")
    password = str(body.get("password") or "")
    try:
        result = auth_service.register(username, email, password, ip=ip)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail)
    return JSONResponse(
        {
            "status": "verification_sent",
            "email": result["email"],
            "delivery": result["delivery"],
        }
    )


@router.post("/auth/resend-verification")
async def auth_resend_verification(request: Request):
    ip = _client_ip(request)
    allowed, _ = redis_client.rate_limit("resend", ip, limit=5, window_seconds=3600)
    if allowed:
        body = await _json_body(request)
        auth_service.resend_verification(str(body.get("email") or ""))
    # Neutral response — never reveal whether the email exists.
    return {"status": "sent"}


@router.post("/auth/verify")
async def auth_verify(request: Request):
    body = await _json_body(request)
    try:
        auth_service.verify(str(body.get("token") or ""))
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail)
    return {"status": "ok"}


@router.post("/auth/forgot-password")
async def auth_forgot_password(request: Request):
    ip = _client_ip(request)
    allowed, _ = redis_client.rate_limit("forgot", ip, limit=5, window_seconds=3600)
    if allowed:
        body = await _json_body(request)
        auth_service.forgot_password(str(body.get("email") or ""), ip=ip)
    # Neutral response — reset links are emailed only, never returned here.
    return {"status": "sent"}


@router.post("/auth/reset-password")
async def auth_reset_password(request: Request):
    body = await _json_body(request)
    try:
        auth_service.reset_password(
            str(body.get("token") or ""), str(body.get("password") or "")
        )
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail)
    return {"status": "ok"}


@router.get("/me")
async def me(request: Request):
    user = _require(request)
    return _me_view(user)


@router.get("/orgs/current")
async def orgs_current(request: Request):
    user = _require(request)
    return _org_view(user)


# ---------------------------------------------------------------------------
# Dashboard / metrics
# ---------------------------------------------------------------------------

def _dashboard_payload(user: User) -> dict[str, Any]:
    db = SessionLocal()
    try:
        scans = (
            db.query(ScanRun)
            .filter_by(user_id=user.id)
            .order_by(ScanRun.started_at.desc())
            .all()
        )
        latest = scans[0] if scans else None
        total_scans = len(scans)
        connections = db.query(Connection).filter_by(user_id=user.id).all()
        conn_ok = sum(1 for c in connections if (c.status or "") == "ok")

        repos_total = latest.total_repos if latest else 0
        healthy = latest.healthy if latest else 0
        degraded = latest.degraded if latest else 0
        down = latest.down if latest else 0
        repaired = latest.repaired if latest else 0

        # Fleet health distribution derived from the latest scan's buckets.
        # Bands match what Overview.jsx expects: "90-100", "70-89",
        # "50-69", "<50".
        fleet_health = [
            {"band": "90-100", "count": healthy},
            {"band": "70-89", "count": degraded},
            {"band": "50-69", "count": 0},
            {"band": "<50", "count": down},
        ]

        kpis = {
            "repos_total": repos_total,
            "open_findings": 0,
            "auto_fix_success_rate": (repaired / repos_total) if repos_total else None,
            "sample_size": repaired,
            "mttr_seconds_avg": None,
            "usd_per_repair_avg": 0,
            "regression_rate": None,
            "connections_ok": conn_ok,
            "scans_total": total_scans,
        }

        repair_cost = {
            "month_label": None,
            "spend_usd": 0,
        }

        return {
            "kpis": kpis,
            "fleet_health": fleet_health,
            "repair_cost": repair_cost,
            "activity": [],
            "awaiting_approval": [],
        }
    finally:
        db.close()


@router.get("/dashboard")
async def dashboard(request: Request):
    user = _require(request)
    return _dashboard_payload(user)


@router.get("/metrics/dashboard")
async def metrics_dashboard(request: Request):
    # Alias: some SPA builds reference /v1/metrics/dashboard.
    user = _require(request)
    return _dashboard_payload(user)


# ---------------------------------------------------------------------------
# Integrations (real: the user's Connection rows)
# ---------------------------------------------------------------------------

def _integration_status(status: str | None) -> str:
    # SPA Settings statusTone(): active|revoked|error|<other>.
    s = (status or "unknown").lower()
    if s == "ok":
        return "active"
    if s == "error":
        return "error"
    return "info"


def _ensure_connections(user_id: str) -> None:
    """Create the default provider Connection rows if absent (mirrors the
    Connections page behaviour) so the SPA Settings surface shows the real
    OllaBridge / GitPilot / MatrixLab integrations instead of an empty list.
    """
    db = SessionLocal()
    try:
        existing = {c.provider for c in db.query(Connection).filter_by(user_id=user_id).all()}
        created = False
        for provider in clients.PROVIDERS:
            if provider not in existing:
                db.add(
                    Connection(
                        user_id=user_id,
                        provider=provider,
                        base_url=clients.DEFAULTS[provider],
                        status="unknown",
                    )
                )
                created = True
        if created:
            db.commit()
    finally:
        db.close()


@router.get("/integrations")
async def integrations(request: Request):
    user = _require(request)
    _ensure_connections(user.id)
    db = SessionLocal()
    try:
        rows = db.query(Connection).filter_by(user_id=user.id).all()
        # Ensure deterministic ordering by the known provider list.
        by_provider = {c.provider: c for c in rows}
        items = []
        for provider in clients.PROVIDERS:
            c = by_provider.get(provider)
            if c is None:
                continue
            items.append(
                {
                    "id": c.id,
                    "provider": c.provider,
                    "display_name": clients.PROVIDER_LABELS.get(c.provider, c.provider),
                    "account": c.base_url or clients.DEFAULTS.get(c.provider, ""),
                    "status": _integration_status(c.status),
                    "deleted_at": None,
                    "has_secret": bool(crypto.decrypt(c.api_key_enc or "")),
                    "last_checked_at": c.last_checked_at.isoformat() if c.last_checked_at else None,
                }
            )
        return {"items": items, "count": len(items), "total": len(items)}
    finally:
        db.close()


@router.get("/integrations/{integration_id}")
async def integration_detail(request: Request, integration_id: str):
    user = _require(request)
    db = SessionLocal()
    try:
        c = db.query(Connection).filter_by(user_id=user.id, id=integration_id).first()
        if not c:
            raise HTTPException(status_code=404, detail="Integration not found")
        return {
            "id": c.id,
            "provider": c.provider,
            "display_name": clients.PROVIDER_LABELS.get(c.provider, c.provider),
            "account": c.base_url or clients.DEFAULTS.get(c.provider, ""),
            "status": _integration_status(c.status),
            "deleted_at": None,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Connections (OllaBridge / GitPilot / MatrixLab) — session-auth JSON for the
# React console's Connections surface. Mirrors main._connection_view + the
# save/test logic so the green /connections page can be fully retired.
# ---------------------------------------------------------------------------

def _connection_view(conn: Connection) -> dict[str, Any]:
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


@router.get("/connections")
async def connections_list(request: Request):
    user = _require(request)
    _ensure_connections(user.id)
    db = SessionLocal()
    try:
        rows = {c.provider: c for c in db.query(Connection).filter_by(user_id=user.id).all()}
        return [_connection_view(rows[p]) for p in clients.PROVIDERS if p in rows]
    finally:
        db.close()


@router.post("/connections/{provider}")
async def connections_save(request: Request, provider: str):
    user = _require(request)
    if provider not in clients.PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown provider")
    _ensure_connections(user.id)
    body = await _json_body(request)
    base_url = str(body.get("base_url") or "")
    api_key = str(body.get("api_key") or "")
    db = SessionLocal()
    try:
        conn = db.query(Connection).filter_by(user_id=user.id, provider=provider).first()
        conn.base_url = (base_url or clients.DEFAULTS[provider]).strip()
        if api_key.strip():
            conn.api_key_enc = crypto.encrypt(api_key.strip())
        secret = crypto.decrypt(conn.api_key_enc or "")
        result = clients.test_provider(provider, conn.base_url, secret)
        conn.status = result["status"]
        conn.detail = result["detail"]
        conn.last_checked_at = datetime.now(timezone.utc)
        db.add(AuditLog(user_id=user.id, action=f"connection_saved:{provider}", details=result["status"]))
        db.commit()
        return {"ok": True, **result}
    finally:
        db.close()


@router.post("/connections/{provider}/test")
async def connections_test(request: Request, provider: str):
    user = _require(request)
    if provider not in clients.PROVIDERS:
        raise HTTPException(status_code=404, detail="Unknown provider")
    _ensure_connections(user.id)
    db = SessionLocal()
    try:
        conn = db.query(Connection).filter_by(user_id=user.id, provider=provider).first()
        secret = crypto.decrypt(conn.api_key_enc or "")
        result = clients.test_provider(provider, conn.base_url or clients.DEFAULTS[provider], secret)
        conn.status = result["status"]
        conn.detail = result["detail"]
        conn.last_checked_at = datetime.now(timezone.utc)
        db.commit()
        return result
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Audit (real: AuditLog rows)
# ---------------------------------------------------------------------------

@router.get("/audit")
async def audit(
    request: Request,
    actor: str | None = None,
    action: str | None = None,
    target_type: str | None = None,
    limit: int = 100,
):
    user = _require(request)
    db = SessionLocal()
    try:
        q = db.query(AuditLog)
        # Admins see the whole org's trail; users see their own actions.
        if user.role != "admin":
            q = q.filter(AuditLog.user_id == user.id)
        if action:
            q = q.filter(AuditLog.action.like(f"%{action}%"))
        rows = q.order_by(AuditLog.created_at.desc()).limit(max(1, min(limit, 500))).all()

        items = []
        for r in rows:
            items.append(
                {
                    "id": r.id,
                    "actor": r.user_id or "system",
                    "action": r.action,
                    "target_type": "",
                    "target_id": r.details or "",
                    "ts": r.created_at.isoformat() if r.created_at else None,
                }
            )
        # actor filter is applied post-hoc since AuditLog stores user_id.
        if actor:
            items = [i for i in items if actor.lower() in str(i["actor"]).lower()]
        return {"items": items, "count": len(items), "total": len(items)}
    finally:
        db.close()


@router.get("/audit/scopes/{scope}/{scope_id}")
async def audit_scope(request: Request, scope: str, scope_id: str, limit: int = 100):
    _require(request)
    return _empty_list()


@router.get("/audit/{audit_id}")
async def audit_detail(request: Request, audit_id: str):
    user = _require(request)
    db = SessionLocal()
    try:
        r = db.query(AuditLog).filter_by(id=audit_id).first()
        if not r:
            raise HTTPException(status_code=404, detail="Audit entry not found")
        if user.role != "admin" and r.user_id != user.id:
            raise HTTPException(status_code=404, detail="Audit entry not found")
        return {
            "id": r.id,
            "actor": r.user_id or "system",
            "action": r.action,
            "target_type": "",
            "target_id": r.details or "",
            "ts": r.created_at.isoformat() if r.created_at else None,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Honest empty collections for surfaces with no backing data yet.
# Each returns the exact {items, count, next_cursor} shape the SPA reads.
# ---------------------------------------------------------------------------

@router.get("/repos")
async def repos(request: Request):
    _require(request)
    return _empty_list()


@router.get("/repos/sync")
@router.post("/repos/sync")
async def repos_sync(request: Request):
    _require(request)
    return {"items": [], "count": 0, "synced": 0}


# ---------------------------------------------------------------------------
# Control-plane intake + read endpoints (Messages / Jobs / Notifications)
# ---------------------------------------------------------------------------

def _audit_row(action: str, user_id: str | None = None, details: str | None = None) -> None:
    db = SessionLocal()
    try:
        db.add(AuditLog(user_id=user_id, action=action, details=details))
        db.commit()
    finally:
        db.close()


def _job_view(job: Job) -> dict[str, Any]:
    """Map a Job row into the shape the SPA Jobs surface reads.

    Jobs.jsx expects: id, repo.full_name / repo_id, trigger, state,
    started_at, finished_at, error_kind. We add health_score (unused by the
    base surface but available to richer views).
    """
    owner, repo = parse_owner_repo(job.repo_url)
    full_name = "/".join(p for p in (owner, repo) if p) or job.repo_url
    return {
        "id": job.id,
        "repo": {"full_name": full_name},
        "repo_id": full_name,
        "repo_url": job.repo_url,
        "branch": job.branch,
        "trigger": "intake",
        "state": job.status,
        "health_score": job.health_score,
        "started_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "error_kind": (job.error.split(":", 1)[0] if job.error else None),
    }


@router.post("/plans", status_code=202)
async def submit_plan(request: Request):
    client_id, kind = resolve_client(request)

    allowed, _ = redis_client.rate_limit("plans", client_id, limit=60, window_seconds=3600)
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    repo_url = str(body.get("repo_url") or "").strip()
    if not repo_url:
        raise HTTPException(status_code=400, detail="repo_url is required")
    mtype = str(body.get("type") or "maintenance_request").strip()
    branch = str(body.get("branch") or "main").strip() or "main"
    mode = str(body.get("mode") or "dry_run").strip() or "dry_run"
    text_message = body.get("message")
    requested_by = body.get("requested_by")
    plan = body.get("plan")

    idem = request.headers.get("idempotency-key") or body.get("idempotency_key")
    idem = str(idem).strip() if idem else None

    db = SessionLocal()
    try:
        # Idempotency: return the existing message instead of creating a new one.
        if idem:
            existing = (
                db.query(Message)
                .filter_by(idempotency_key=idem, client_id=client_id)
                .order_by(Message.created_at.desc())
                .first()
            )
            if existing:
                return JSONResponse(
                    {
                        "id": existing.id,
                        "message_id": existing.id,
                        "job_id": existing.job_id,
                        "status": existing.status,
                        "idempotent": True,
                    },
                    status_code=200,
                )

        owner, repo = parse_owner_repo(repo_url)
        owner_repo = "/".join(p for p in (owner, repo) if p) or repo_url

        msg = Message(
            client_id=client_id,
            requested_by=str(requested_by) if requested_by else None,
            type=mtype,
            repo_url=repo_url,
            branch=branch,
            mode=mode,
            message=str(text_message) if text_message else None,
            payload=json.dumps(plan, default=str) if plan is not None else None,
            idempotency_key=idem,
            status="queued",
        )
        db.add(msg)
        db.flush()  # assign msg.id

        job = Job(message_id=msg.id, repo_url=repo_url, branch=branch, status="queued")
        db.add(job)
        db.flush()  # assign job.id
        msg.job_id = job.id

        db.add(
            Notification(
                source=client_id,
                kind="request_received",
                title=f"{client_id} requested: {mtype} · {owner_repo}",
                body=str(text_message) if text_message else None,
                link=job.id,
            )
        )
        # Audit (no secrets/tokens).
        actor_id = request.session.get("user_id") if kind == "user" else None
        db.add(
            AuditLog(
                user_id=actor_id,
                action="plan_submitted",
                details=f"{client_id}:{mtype}:{owner_repo}",
            )
        )
        db.commit()
        message_id = msg.id
        job_id = job.id
    finally:
        db.close()

    # Kick off the real health check in the background.
    start_health_job(job_id)

    return JSONResponse(
        {"id": message_id, "message_id": message_id, "job_id": job_id, "status": "queued"},
        status_code=202,
    )


@router.get("/inbox")
async def inbox(request: Request):
    # Session OR service auth (both can read the single-tenant inbox).
    user = _current_user(request)
    if not user:
        resolve_client(request)  # raises 401 unless a valid ingest token is present
    db = SessionLocal()
    try:
        rows = db.query(Message).order_by(Message.created_at.desc()).limit(200).all()
        job_ids = [m.job_id for m in rows if m.job_id]
        jobs_by_id = {}
        if job_ids:
            for j in db.query(Job).filter(Job.id.in_(job_ids)).all():
                jobs_by_id[j.id] = j
        items = []
        for m in rows:
            job = jobs_by_id.get(m.job_id) if m.job_id else None
            items.append(
                {
                    "id": m.id,
                    "client_id": m.client_id,
                    "requested_by": m.requested_by,
                    "type": m.type,
                    "repo_url": m.repo_url,
                    "branch": m.branch,
                    "mode": m.mode,
                    "status": m.status,
                    "job_id": m.job_id,
                    "health_score": job.health_score if job else None,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
            )
        return {"items": items, "count": len(items)}
    finally:
        db.close()


@router.get("/jobs")
async def jobs(request: Request, limit: int = 100):
    _require(request)
    db = SessionLocal()
    try:
        rows = (
            db.query(Job)
            .order_by(Job.created_at.desc())
            .limit(max(1, min(limit, 500)))
            .all()
        )
        items = [_job_view(j) for j in rows]
        return {"items": items, "count": len(items), "total": len(items), "next_cursor": None}
    finally:
        db.close()


@router.get("/jobs/{job_id}")
async def job_detail(request: Request, job_id: str):
    _require(request)
    db = SessionLocal()
    try:
        job = db.query(Job).filter_by(id=job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        view = _job_view(job)
        report = None
        if job.report_json:
            try:
                report = json.loads(job.report_json)
            except Exception:
                report = None
        view["report"] = report
        view["report_json"] = job.report_json
        view["error"] = job.error
        return view
    finally:
        db.close()


@router.get("/notifications")
async def notifications(request: Request, unread: int = 0):
    _require(request)
    db = SessionLocal()
    try:
        q = db.query(Notification)
        if unread:
            q = q.filter(Notification.read == False)  # noqa: E712
        rows = q.order_by(Notification.created_at.desc()).limit(100).all()
        unread_count = db.query(Notification).filter(Notification.read == False).count()  # noqa: E712
        items = [
            {
                "id": n.id,
                "source": n.source,
                "kind": n.kind,
                "title": n.title,
                "body": n.body,
                "link": n.link,
                "read": bool(n.read),
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in rows
        ]
        return {"items": items, "unread_count": unread_count}
    finally:
        db.close()


@router.post("/notifications/{notif_id}/read")
async def notification_read(request: Request, notif_id: str):
    _require(request)
    db = SessionLocal()
    try:
        n = db.query(Notification).filter_by(id=notif_id).first()
        if not n:
            raise HTTPException(status_code=404, detail="Notification not found")
        n.read = True
        db.commit()
        unread_count = db.query(Notification).filter(Notification.read == False).count()  # noqa: E712
        return {"ok": True, "unread_count": unread_count}
    finally:
        db.close()


@router.post("/notifications/read-all")
async def notifications_read_all(request: Request):
    _require(request)
    db = SessionLocal()
    try:
        db.query(Notification).filter(Notification.read == False).update(  # noqa: E712
            {"read": True}, synchronize_session=False
        )
        db.commit()
        return {"ok": True, "unread_count": 0}
    finally:
        db.close()


@router.get("/findings")
async def findings(request: Request):
    _require(request)
    return _empty_list()


@router.get("/repairs")
async def repairs(request: Request):
    _require(request)
    return _empty_list()


@router.get("/policies")
async def policies(request: Request):
    _require(request)
    return _empty_list()


@router.get("/policies/decisions")
async def policy_decisions(request: Request):
    _require(request)
    return _empty_list()


@router.get("/issues")
async def issues(request: Request):
    _require(request)
    return _empty_list()


@router.get("/schedules")
async def schedules(request: Request):
    _require(request)
    # listSchedules() reads the array directly; surfaces tolerate {items}
    # too, but the hook expects a bare list per schedules.js usage. Return
    # an empty array to match listSchedules() -> data.
    return []


# ---------------------------------------------------------------------------
# Admin (role-gated): user management, full audit, system status.
# Every endpoint is gated by ``_require_admin`` which enforces RBAC on the
# server (never trust the UI). Mutations are audited; secrets are never logged.
# ---------------------------------------------------------------------------

def _admin_user_view(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role or "user",
        "is_active": bool(user.is_active),
        "email_verified": bool(user.email_verified),
        "is_root": bool(getattr(user, "is_root", False)),
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


def _active_admin_count(db, exclude_id: str | None = None) -> int:
    q = db.query(User).filter(User.role == "admin", User.is_active == True)  # noqa: E712
    if exclude_id:
        q = q.filter(User.id != exclude_id)
    return q.count()


@router.get("/admin/stats")
async def admin_stats(request: Request):
    _require_admin(request)
    db = SessionLocal()
    try:
        total = db.query(User).count()
        verified = db.query(User).filter(User.email_verified == True).count()  # noqa: E712
        active = db.query(User).filter(User.is_active == True).count()  # noqa: E712
        admins = db.query(User).filter(User.role == "admin").count()
        messages = db.query(Message).count()
        jobs = db.query(Job).count()
        unread = db.query(Notification).filter(Notification.read == False).count()  # noqa: E712
        recent = (
            db.query(User).order_by(User.created_at.desc()).limit(5).all()
        )
        recent_signups = [
            {
                "id": u.id,
                "email": u.email,
                "username": u.username,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in recent
        ]
        return {
            "users": {
                "total": total,
                "verified": verified,
                "active": active,
                "admins": admins,
            },
            "messages": messages,
            "jobs": jobs,
            "notifications_unread": unread,
            "backends": {
                "db": engine.dialect.name,
                "redis": redis_client.configured(),
                "email": email_service.configured(),
            },
            "recent_signups": recent_signups,
        }
    finally:
        db.close()


@router.get("/admin/users")
async def admin_users(
    request: Request,
    query: str | None = None,
    limit: int = 25,
    offset: int = 0,
):
    _require_admin(request)
    limit = max(1, min(int(limit or 25), 100))
    offset = max(0, int(offset or 0))
    db = SessionLocal()
    try:
        q = db.query(User)
        if query:
            like = f"%{query.strip().lower()}%"
            from sqlalchemy import func, or_

            q = q.filter(
                or_(
                    func.lower(User.email).like(like),
                    func.lower(User.username).like(like),
                    func.lower(func.coalesce(User.display_name, "")).like(like),
                )
            )
        count = q.count()
        rows = (
            q.order_by(User.created_at.desc()).offset(offset).limit(limit).all()
        )
        return {
            "items": [_admin_user_view(u) for u in rows],
            "count": count,
            "limit": limit,
            "offset": offset,
        }
    finally:
        db.close()


@router.get("/admin/users/{user_id}")
async def admin_user_detail(request: Request, user_id: str):
    _require_admin(request)
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(id=user_id).first()
        if not u:
            raise HTTPException(status_code=404, detail="User not found")
        connections = db.query(Connection).filter_by(user_id=user_id).count()
        acts = (
            db.query(AuditLog)
            .filter(AuditLog.user_id == user_id)
            .order_by(AuditLog.created_at.desc())
            .limit(20)
            .all()
        )
        recent_activity = [
            {
                "action": a.action,
                "details": a.details or "",
                "ts": a.created_at.isoformat() if a.created_at else None,
            }
            for a in acts
        ]
        view = _admin_user_view(u)
        view["connections"] = connections
        view["recent_activity"] = recent_activity
        return view
    finally:
        db.close()


@router.patch("/admin/users/{user_id}")
async def admin_user_update(request: Request, user_id: str):
    admin = _require_admin(request)
    body = await _json_body(request)
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(id=user_id).first()
        if not u:
            raise HTTPException(status_code=404, detail="User not found")

        new_role = body.get("role")
        new_active = body.get("is_active")
        new_verified = body.get("email_verified")

        # The root superuser is immutable (cannot be demoted or deactivated).
        if getattr(u, "is_root", False):
            role_change = new_role is not None and str(new_role) != (u.role or "user")
            active_change = new_active is not None and bool(new_active) != bool(u.is_active)
            if role_change or active_change:
                raise HTTPException(
                    status_code=400,
                    detail="The root superuser is protected and cannot be demoted or deactivated.",
                )

        # Guards.
        if new_role is not None and str(new_role) != (u.role or "user"):
            if u.id == admin.id:
                raise HTTPException(status_code=400, detail="You cannot change your own role.")
            if str(new_role) not in ("user", "admin"):
                raise HTTPException(status_code=400, detail="Role must be 'user' or 'admin'.")
            # Demoting an admin: ensure at least one other active admin remains.
            if (u.role or "user") == "admin" and str(new_role) != "admin":
                if _active_admin_count(db, exclude_id=u.id) == 0:
                    raise HTTPException(status_code=400, detail="Cannot demote the last remaining admin.")
        if new_active is not None and bool(new_active) is False:
            if u.id == admin.id:
                raise HTTPException(status_code=400, detail="You cannot deactivate yourself.")
            if (u.role or "user") == "admin" and _active_admin_count(db, exclude_id=u.id) == 0:
                raise HTTPException(status_code=400, detail="Cannot deactivate the last remaining admin.")

        diff = {}
        if new_role is not None and str(new_role) != (u.role or "user"):
            diff["role"] = f"{u.role or 'user'}->{new_role}"
            u.role = str(new_role)
        if new_active is not None and bool(new_active) != bool(u.is_active):
            diff["is_active"] = f"{bool(u.is_active)}->{bool(new_active)}"
            u.is_active = bool(new_active)
        if new_verified is not None and bool(new_verified) != bool(u.email_verified):
            diff["email_verified"] = f"{bool(u.email_verified)}->{bool(new_verified)}"
            u.email_verified = bool(new_verified)

        if diff:
            db.add(
                AuditLog(
                    user_id=admin.id,
                    action="admin_user_updated",
                    details=f"{u.id}:{json.dumps(diff)}",
                    ip_address=_client_ip(request),
                )
            )
        db.commit()
        return _admin_user_view(u)
    finally:
        db.close()


@router.post("/admin/users/{user_id}/send-reset")
async def admin_send_reset(request: Request, user_id: str):
    admin = _require_admin(request)
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(id=user_id).first()
        if not u:
            raise HTTPException(status_code=404, detail="User not found")
        target_email = u.email
    finally:
        db.close()
    # Reuse the shared reset-token + email logic (mints token, emails link,
    # audits "password_reset_requested"). Never surfaces the link.
    auth_service.forgot_password(target_email, ip=_client_ip(request))
    _audit_row(
        action="admin_sent_reset",
        user_id=admin.id,
        details=f"{user_id}",
    )
    return {"status": "sent"}


@router.delete("/admin/users/{user_id}")
async def admin_user_delete(request: Request, user_id: str):
    admin = _require_admin(request)
    db = SessionLocal()
    try:
        u = db.query(User).filter_by(id=user_id).first()
        if not u:
            raise HTTPException(status_code=404, detail="User not found")
        if getattr(u, "is_root", False):
            raise HTTPException(status_code=400, detail="The root superuser cannot be deleted.")
        if u.id == admin.id:
            raise HTTPException(status_code=400, detail="You cannot delete yourself.")
        if (u.role or "user") == "admin" and _active_admin_count(db, exclude_id=u.id) == 0:
            raise HTTPException(status_code=400, detail="Cannot delete the last remaining admin.")

        email = u.email
        # Cleanup the user's Connections (FK -> users.id). ScanRuns cascade via
        # the relationship. Keep the AuditLog trail: null the FK so the history
        # survives the user deletion (AuditLog.user_id is nullable).
        db.query(Connection).filter_by(user_id=user_id).delete(synchronize_session=False)
        db.query(AuditLog).filter_by(user_id=user_id).update(
            {AuditLog.user_id: None}, synchronize_session=False
        )
        db.delete(u)
        db.add(
            AuditLog(
                user_id=admin.id,
                action="admin_user_deleted",
                details=f"{user_id}:{email}",
                ip_address=_client_ip(request),
            )
        )
        db.commit()
        return {"status": "deleted", "id": user_id}
    finally:
        db.close()


@router.get("/admin/audit")
async def admin_audit(
    request: Request,
    query: str | None = None,
    actor: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    _require_admin(request)
    limit = max(1, min(int(limit or 50), 200))
    offset = max(0, int(offset or 0))
    db = SessionLocal()
    try:
        q = db.query(AuditLog)
        if query:
            q = q.filter(AuditLog.action.like(f"%{query.strip()}%"))
        if actor:
            q = q.filter(AuditLog.user_id == actor.strip())
        count = q.count()
        rows = (
            q.order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        items = [
            {
                "id": r.id,
                "actor": r.user_id or "system",
                "action": r.action,
                "details": r.details or "",
                "ts": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]
        return {"items": items, "count": count, "limit": limit, "offset": offset}
    finally:
        db.close()
