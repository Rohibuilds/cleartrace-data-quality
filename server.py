"""ClearTrace — Production FastAPI Server.

Provides REST API endpoints for data quality scanning, autonomous repair review,
cryptographic passports, dataset time machine, and serves the PWA frontend.
"""

from __future__ import annotations

import io
import json
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, File, HTTPException, Query, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from cleartrace.ingest import (
    parse_csv_bytes,
    parse_document_bytes,
    load_demo_dataset,
    load_math_demo_dataset,
    IngestionError,
)
from cleartrace.scan import scan_dataset
from cleartrace.repair import generate_proposal
from cleartrace.audit import SessionManager, StaleRevisionError
from cleartrace.scoring import calculate_quality_score, rank_proposals
from cleartrace.passport import generate_data_passport, simulate_impact, compute_df_sha256
from cleartrace.export import export_cleaned_csv, export_findings_report, export_audit_log, export_comprehensive_report
from cleartrace.math_engine import inspect_invoice_dataset, convert_math_findings_to_proposals
from cleartrace.retrieval import build_session_evidence_index
from cleartrace.llm_assistant import get_llm_status, ask_knowledge_assistant
from cleartrace.persistence import (
    save_encrypted_session,
    load_encrypted_session,
    delete_encrypted_session,
    get_storage_dir,
    get_session_dir,
    AuthenticationError,
    SecurityStorageError,
)
from cleartrace.auth import (
    request_code, verify_code, get_user, logout as logout_auth_session,
    create_public_demo, get_public_demo, get_role, set_user_role,
    google_authorization_url, consume_oauth_state, exchange_google_code,
    verify_google_id_token, create_google_session, smtp_delivery_enabled, email_delivery_enabled,
    notify_owner_activity,
)

import secrets
import re
import time
import logging
from collections import defaultdict
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("cleartrace.server")

app = FastAPI(
    title="ClearTrace API",
    version="2.3.6",
    description="Autonomous Data Quality and Traceable Repair Engine",
)

# ── Security Middleware & Headers ───────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# In-memory sliding-window rate limiter (180 requests/minute per client IP)
_RATE_LIMIT_STORE: Dict[str, List[float]] = defaultdict(list)
_RATE_LIMIT_MAX_REQUESTS = 180
_RATE_LIMIT_WINDOW_SECONDS = 60.0

class RateLimitingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/") and not path.startswith("/api/health"):
            client_ip = request.headers.get("x-forwarded-for")
            if client_ip:
                client_ip = client_ip.split(",")[0].strip()
            else:
                client_ip = request.client.host if request.client else "unknown"

            now = time.time()
            timestamps = _RATE_LIMIT_STORE[client_ip]
            cutoff = now - _RATE_LIMIT_WINDOW_SECONDS
            active_ts = [ts for ts in timestamps if ts > cutoff]
            _RATE_LIMIT_STORE[client_ip] = active_ts

            if len(active_ts) >= _RATE_LIMIT_MAX_REQUESTS:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Maximum 180 requests per minute."},
                    headers={"Retry-After": "60"},
                )
            _RATE_LIMIT_STORE[client_ip].append(now)

        return await call_next(request)

app.add_middleware(RateLimitingMiddleware)

# Allowed local dev/demo origins (no wildcard with credentials per OWASP ASVS)
ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:8501",
    "http://127.0.0.1:8501",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"^https:\/\/.*(\.up\.railway\.app|\.railway\.app|\.onrender\.com|\.trycloudflare\.com)$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Session-ID", "Content-Disposition"],
)

# ── Isolated Multi-Tenant Session Management ────────────────────────────────

SAFE_SESSION_TOKEN_REGEX = re.compile(r"^[a-zA-Z0-9_\-]{8,64}$")
current_session_token: ContextVar[str] = ContextVar("current_session_token", default="default-session")
SESSION_STORE: Dict[str, SessionManager] = {}

# CSRF: State-mutating endpoints that require origin validation.
# OWASP ASVS v4.0.3 / v5.0 Cross-Site Request Forgery Defenses:
# Validates Origin, Referer, and Sec-Fetch-Site to guarantee requests originate from trusted frontends.
_CSRF_PROTECTED_PATHS: set = {
    "/api/repair/apply",
    "/api/repair/batch-apply",
    "/api/repair/reject-notice",
    "/api/math/validate",
    "/api/audit/undo",
    "/api/audit/reset",
    "/api/dataset/upload",
    "/api/dataset/demo",
    "/api/auth/request-code",
    "/api/auth/verify",
    "/api/auth/logout",
    "/api/auth/public-demo",
    "/api/auth/role",
}
_PUBLIC_DEMO_MUTATION_PATHS: set = {
    "/api/dataset/demo", "/api/dataset/math-demo",
    "/api/repair/apply", "/api/repair/batch-apply",
    "/api/repair/reject-notice",
    "/api/math/validate",
    "/api/audit/undo", "/api/audit/reset",
    "/api/timemachine/compare", "/api/timemachine/restore",
    "/api/math/rules",
    "/api/rag/search", "/api/rag/ask",
}
_ROLE_PROTECTED_MUTATIONS: set = {
    "/api/dataset/upload", "/api/dataset/demo", "/api/dataset/math-demo",
    "/api/repair/apply", "/api/repair/batch-apply", "/api/audit/undo",
    "/api/repair/reject-notice",
    "/api/math/validate",
    "/api/audit/reset", "/api/timemachine/restore", "/api/math/rules",
}


def is_trusted_origin(origin: str, host: str = "") -> bool:
    origin_clean = origin.rstrip("/").lower()
    for allowed in ALLOWED_ORIGINS:
        if origin_clean == allowed.rstrip("/").lower():
            return True
    if origin_clean in ("http://testserver", "https://testserver"):
        return True
    if re.match(r"^https:\/\/[a-zA-Z0-9\-]+\.trycloudflare\.com$", origin_clean):
        return True
    if re.match(r"^https:\/\/[a-zA-Z0-9\-]+\.(up\.)?railway\.app$", origin_clean):
        return True
    if re.match(r"^https:\/\/[a-zA-Z0-9\-]+\.onrender\.com$", origin_clean):
        return True
    extra_origins = os.environ.get("CLEARTRACE_ALLOWED_ORIGINS", "")
    if extra_origins:
        for extra in extra_origins.split(","):
            if extra.strip() and origin_clean == extra.strip().rstrip("/").lower():
                return True
    return False


def persist_session(token: Optional[str] = None, sm: Optional[SessionManager] = None) -> None:
    tok = token or current_session_token.get()
    mgr = sm or SESSION_STORE.get(tok)
    if tok and mgr:
        try:
            save_encrypted_session(tok, mgr)
        except Exception as exc:
            logger.exception("Session persistence failed for %s", tok[:8])
            raise HTTPException(status_code=503, detail="Workspace changes could not be saved. Please retry after storage recovers.") from exc


class SessionIsolationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        auth_token = request.cookies.get("ct_auth_session", "")
        auth_user = get_user(auth_token)
        public_demo = get_public_demo(request.cookies.get("ct_public_demo"))
        auth_enabled = os.environ.get("CLEARTRACE_AUTH_ENABLED", "true").lower() not in ("false", "0", "no")
        auth_public_paths = {
            "/api/health", "/api/auth/status", "/api/auth/request-code",
            "/api/auth/verify", "/api/auth/logout", "/api/auth/public-demo",
            "/api/auth/google/start", "/api/auth/google/callback", "/api/auth/role",
        }
        anonymous_auth_request = auth_enabled and path in auth_public_paths and not auth_user and not public_demo
        if auth_enabled and path.startswith("/api/"):
            if path not in auth_public_paths and not auth_user and not public_demo:
                from fastapi.responses import JSONResponse as _JSONResponse
                return _JSONResponse(status_code=401, content={"detail": "Sign in with an email verification code, or open the sample evaluation workspace."})
            if public_demo and request.method not in ("GET", "HEAD", "OPTIONS") and path not in _PUBLIC_DEMO_MUTATION_PATHS:
                from fastapi.responses import JSONResponse as _JSONResponse
                return _JSONResponse(status_code=403, content={"detail": "Uploads are disabled in the public sample workspace. Sign in by email to use your own files."})
            protected_write = path in _ROLE_PROTECTED_MUTATIONS or path.startswith("/api/math/rules/")
            if auth_user and request.method in ("POST", "PUT", "PATCH", "DELETE") and protected_write and auth_user.get("role") == "viewer":
                return JSONResponse(status_code=403, content={"detail": "Your workspace role is read-only. Ask an owner or admin to change your role."})
        cookie_token = request.cookies.get("ct_session_id")
        header_token = request.headers.get("X-Session-ID")

        # When request is proxied through public reverse proxies (Cloudflare Tunnel or Railway proxy),
        # external internet callers cannot supply arbitrary X-Session-ID to hijack
        # sessions. In that public context, only the HttpOnly cookie is trusted.
        # In local/test environments (no public proxy headers), accept X-Session-ID header for test client isolation.
        is_public_proxy = bool(
            request.headers.get("cf-ray")
            or request.headers.get("x-railway-request-id")
        )
        if auth_enabled and auth_user:
            raw_token = auth_user["workspace_id"]
        elif auth_enabled and public_demo:
            raw_token = public_demo["workspace_id"]
        elif is_public_proxy:
            raw_token = cookie_token
        else:
            raw_token = header_token or cookie_token

        if not raw_token or not SAFE_SESSION_TOKEN_REGEX.match(raw_token):
            token = secrets.token_hex(16)
        else:
            token = raw_token

        if not anonymous_auth_request and token not in SESSION_STORE:
            loaded = None
            try:
                loaded = load_encrypted_session(token)
            except Exception as exc:
                logger.exception("Encrypted workspace load failed for %s", token[:8])
                return JSONResponse(status_code=503, content={"detail": "Workspace storage could not be read. Your saved data was not replaced."})
            if loaded is not None:
                SESSION_STORE[token] = loaded
            else:
                if (get_session_dir() / f"{token}.enc").exists():
                    return JSONResponse(status_code=503, content={"detail": "Saved workspace could not be restored. Contact the app owner; no replacement data was written."})
                sm = SessionManager(load_demo_dataset(), filename="synthetic_quality_issues.csv")
                SESSION_STORE[token] = sm
                try:
                    save_encrypted_session(token, sm)
                except Exception as exc:
                    SESSION_STORE.pop(token, None)
                    logger.exception("Initial workspace save failed for %s", token[:8])
                    return JSONResponse(status_code=503, content={"detail": "Workspace storage is unavailable. Please retry shortly."})

        ctx_token = current_session_token.set(token)
        try:
            # CSRF guard: state-mutating endpoints require verified same-origin or custom header.
            # 1. Reject cross-site requests signaled by modern browsers (Sec-Fetch-Site: cross-site)
            # 2. Reject requests with untrusted Origin header
            # 3. Reject requests with untrusted Referer header
            csrf_protected = request.url.path in _CSRF_PROTECTED_PATHS or request.url.path.startswith("/api/math/rules/")
            if request.method in ("POST", "PUT", "DELETE") and csrf_protected:
                sec_fetch_site = request.headers.get("sec-fetch-site", "").lower()
                if sec_fetch_site == "cross-site":
                    from fastapi.responses import JSONResponse as _JSONResponse
                    return _JSONResponse(
                        status_code=403,
                        content={"detail": "CSRF check failed: Cross-site requests prohibited."},
                    )

                host = request.headers.get("host", "")
                origin = request.headers.get("origin")
                if origin and not is_trusted_origin(origin, host):
                    from fastapi.responses import JSONResponse as _JSONResponse
                    return _JSONResponse(
                        status_code=403,
                        content={"detail": "CSRF check failed: Untrusted Origin."},
                    )

                referer = request.headers.get("referer")
                if referer:
                    from urllib.parse import urlparse
                    ref_parsed = urlparse(referer)
                    ref_origin = f"{ref_parsed.scheme}://{ref_parsed.netloc}"
                    if not is_trusted_origin(ref_origin, host):
                        from fastapi.responses import JSONResponse as _JSONResponse
                        return _JSONResponse(
                            status_code=403,
                            content={"detail": "CSRF check failed: Untrusted Referer."},
                        )

            response = await call_next(request)
            is_https = (
                request.url.scheme == "https"
                or request.headers.get("x-forwarded-proto") == "https"
            )
            if not anonymous_auth_request and request.url.path not in ("/api/auth/verify", "/api/auth/logout"):
                response.headers["X-Session-ID"] = token
                response.set_cookie(
                    key="ct_session_id",
                    value=token,
                    httponly=True,
                    samesite="lax",
                    secure=is_https,
                )
            return response
        finally:
            current_session_token.reset(ctx_token)

app.add_middleware(SessionIsolationMiddleware)


def get_session() -> SessionManager:
    token = current_session_token.get()
    if token not in SESSION_STORE:
        loaded = None
        try:
            loaded = load_encrypted_session(token)
        except Exception as exc:
            logger.debug("Session load fallback suppressed for %s: %s", token[:8], exc)
            loaded = None
        if loaded is not None:
            SESSION_STORE[token] = loaded
        else:
            sm = SessionManager(load_demo_dataset(), filename="synthetic_quality_issues.csv")
            SESSION_STORE[token] = sm
            try:
                save_encrypted_session(token, sm)
            except Exception as exc:
                logger.debug("Session fallback save suppressed for %s: %s", token[:8], exc)
    return SESSION_STORE[token]


# ── Schemas ──────────────────────────────────────────────────────────────────

class ApplyRequest(BaseModel):
    finding_id: str
    expected_revision: int


class RejectRepairRequest(BaseModel):
    finding_id: str


class BatchApplyRequest(BaseModel):
    finding_ids: List[str]
    expected_revision: int


class CompareRequest(BaseModel):
    rev_from: int
    rev_to: int


class RestoreRequest(BaseModel):
    target_revision: int


from cleartrace.models import MathRuleConfig

class MathRuleRequest(BaseModel):
    rule_id: str
    rule_type: str  # "formula", "sum", "percentage", "percentage_change", "constraint", "outlier"
    target_column: Optional[str] = None
    expression: Optional[str] = None
    addend_columns: Optional[List[str]] = None
    part_column: Optional[str] = None
    total_column: Optional[str] = None
    old_column: Optional[str] = None
    new_column: Optional[str] = None
    constraint_type: Optional[str] = None
    constraint_value: Optional[str] = None
    tolerance: str = "0.01"
    decimal_places: int = 2
    rounding_mode: str = "ROUND_HALF_UP"
    severity: str = "High"
    description: Optional[str] = None


class ValidateMathRequest(BaseModel):
    tolerance: float = 0.01
    custom_rules: Optional[List[Dict[str, Any]]] = None


class MathDemoRequest(BaseModel):
    format: str = "csv"


class RAGSearchRequest(BaseModel):
    query: str
    limit: int = 5


class RAGAskRequest(BaseModel):
    question: str
    limit: int = 5



def check_access_authorization(request: Request) -> bool:
    """Compatibility helper: authorization is an email-verified server session."""
    if os.environ.get("CLEARTRACE_AUTH_ENABLED", "true").lower() in ("false", "0", "no"):
        return True
    return get_user(request.cookies.get("ct_auth_session")) is not None


def notify_owner_for_request(request: Request, event: str) -> None:
    """Best-effort content-free email for a meaningful workspace action."""
    try:
        user = get_user(request.cookies.get("ct_auth_session"))
        demo = get_public_demo(request.cookies.get("ct_public_demo"))
        email = user.get("email") if user else ("Public sample workspace" if demo else "Workspace session")
        role = user.get("role", "unknown") if user else ("public demo" if demo else "workspace")
        forwarded = request.headers.get("x-forwarded-for", "")
        ip = forwarded.split(",", 1)[0].strip() if forwarded else (request.client.host if request.client else "unknown")
        notify_owner_activity(email, ip, role, event)
    except Exception:
        logger.exception("Owner activity notification setup failed")


class EmailCodeRequest(BaseModel):
    email: str


class VerifyCodeRequest(BaseModel):
    email: str
    code: str


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
def health_probe() -> Dict[str, Any]:
    """Lightweight unauthenticated container healthcheck probe for Railway/Render orchestrators.
    
    Verifies storage readiness without allocating user sessions, disclosing filenames,
    or leaking secrets.
    """
    storage_ready = False
    try:
        sdir = get_storage_dir()
        storage_ready = sdir.exists() or os.access(str(sdir.parent), os.W_OK)
    except Exception:
        storage_ready = False

    return {
        "status": "healthy",
        "service": "ClearTrace Data Quality Engine",
        "version": "2.3.6",
        "storage": "ready" if storage_ready else "unmounted",
        "llm": "direct-evidence",
    }


@app.get("/api/health")
def health() -> Dict[str, Any]:
    """Health and security profile endpoint."""
    token = current_session_token.get()
    has_session = token in SESSION_STORE
    sm = SESSION_STORE.get(token)
    return {
        "status": "healthy",
        "service": "ClearTrace Data Quality Engine",
        "version": "2.3.6",
        "session_active": has_session,
        "dataset_loaded": sm.filename if sm else None,
        "dataset_revision": sm.dataset_revision if sm else 0,
        "encryption": "AES-256-GCM AEAD disk encryption + SHA-256 integrity active",
        "security_profile": "OWASP ASVS 5.0 Level 1 Compliant",
    }


@app.get("/api/auth/status")
def auth_status(request: Request) -> Dict[str, Any]:
    """Return whether the browser has a valid email-verified session."""
    required = os.environ.get("CLEARTRACE_AUTH_ENABLED", "true").lower() not in ("false", "0", "no")
    user = get_user(request.cookies.get("ct_auth_session")) if required else None
    public_demo = get_public_demo(request.cookies.get("ct_public_demo")) if required else None
    return {
        "auth_required": required,
        "is_authenticated": (user is not None) if required else True,
        "is_public_demo": public_demo is not None,
        "email": user["email"] if user else None,
        "role": user["role"] if user else None,
        "google_sign_in_enabled": bool(os.environ.get("CLEARTRACE_GOOGLE_CLIENT_ID") and os.environ.get("CLEARTRACE_GOOGLE_CLIENT_SECRET")),
        "smtp_delivery_enabled": smtp_delivery_enabled(),
        "email_delivery_enabled": email_delivery_enabled(),
        "email_delivery_provider": "resend" if os.environ.get("CLEARTRACE_RESEND_API_KEY") else ("smtp" if smtp_delivery_enabled() else None),
        "owner_alerts_enabled": bool((os.environ.get("CLEARTRACE_OWNER_EMAIL") or os.environ.get("CLEARTRACE_SMTP_USERNAME")) and email_delivery_enabled()),
    }


@app.post("/api/auth/request-code")
def auth_request_code(payload: EmailCodeRequest, request: Request) -> Dict[str, Any]:
    """Email a short-lived, single-use sign-in code."""
    if not email_delivery_enabled():
        raise HTTPException(
            status_code=503,
            detail="Email sign-in is not configured on this deployment yet. Use the sample workspace or contact the app owner.",
        )
    email = payload.email.strip().lower()
    if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    client_ip = request.headers.get("x-forwarded-for", "")
    if client_ip:
        client_ip = client_ip.split(",", 1)[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"
    try:
        request_code(email, client_ip)
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    notify_owner_activity(email, client_ip, "account", "Email sign-in code requested")
    return {"success": True, "message": "If email delivery is available, a sign-in code is on its way."}


@app.post("/api/auth/verify")
def auth_verify_code(payload: VerifyCodeRequest, request: Request, response: Response) -> Dict[str, Any]:
    """Consume a valid one-time code and establish an account workspace session."""
    try:
        client_ip = request.headers.get("x-forwarded-for", "")
        client_ip = client_ip.split(",", 1)[0].strip() if client_ip else (request.client.host if request.client else "unknown")
        session_token, workspace_id = verify_code(payload.email, payload.code, client_ip)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(
        key="ct_auth_session", value=session_token, httponly=True, secure=is_https,
        samesite="lax", max_age=30 * 86400, path="/",
    )
    response.set_cookie(
        key="ct_session_id", value=workspace_id, httponly=True, secure=is_https,
        samesite="lax", max_age=30 * 86400, path="/",
    )
    return {"success": True, "message": "Signed in successfully."}


@app.get("/api/auth/google/start")
def google_sign_in_start(request: Request, response: Response):
    """Begin Google OpenID Connect login using single-use server-stored state."""
    try:
        base = os.environ.get("CLEARTRACE_PUBLIC_URL", str(request.base_url)).rstrip("/")
        if not base.startswith("https://") and os.environ.get("CLEARTRACE_AUTH_ENABLED", "true").lower() not in ("false", "0", "no"):
            raise RuntimeError("Set CLEARTRACE_PUBLIC_URL to the public HTTPS address before enabling Google sign-in.")
        url, state = google_authorization_url(base)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response = RedirectResponse(url, status_code=302)
    response.set_cookie("ct_google_state", state, httponly=True, secure=secure, samesite="lax", max_age=600, path="/api/auth/google")
    return response


@app.get("/api/auth/google/callback")
def google_sign_in_callback(request: Request):
    """Validate Google state, token signature and claims, then set the session cookie."""
    state = request.query_params.get("state", "")
    code = request.query_params.get("code", "")
    redirect = RedirectResponse("/", status_code=303)
    redirect.delete_cookie("ct_google_state", path="/api/auth/google")
    if not code or not secrets.compare_digest(state, request.cookies.get("ct_google_state", "")) or not consume_oauth_state(state):
        redirect = RedirectResponse("/?auth_error=google", status_code=303)
        redirect.delete_cookie("ct_google_state", path="/api/auth/google")
        return redirect
    try:
        base = os.environ.get("CLEARTRACE_PUBLIC_URL", str(request.base_url)).rstrip("/")
        claims_email = verify_google_id_token(exchange_google_code(code, base + "/api/auth/google/callback"))
        ip = request.headers.get("x-forwarded-for", "")
        ip = ip.split(",", 1)[0].strip() if ip else (request.client.host if request.client else "unknown")
        token, workspace_id = create_google_session(claims_email)
        # Reuse login alert pipeline without storing the network address.
        from cleartrace.auth import _record_login_alert
        _record_login_alert(claims_email, ip)
        secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
        redirect.set_cookie("ct_auth_session", token, httponly=True, secure=secure, samesite="lax", max_age=30 * 86400, path="/")
        redirect.set_cookie("ct_session_id", workspace_id, httponly=True, secure=secure, samesite="lax", max_age=30 * 86400, path="/")
    except Exception:
        logger.exception("Google sign-in failed")
        redirect = RedirectResponse("/?auth_error=google", status_code=303)
        redirect.delete_cookie("ct_google_state", path="/api/auth/google")
    return redirect


class RoleUpdateRequest(BaseModel):
    email: str
    role: str


@app.post("/api/auth/role")
def update_account_role(payload: RoleUpdateRequest, request: Request):
    """Owner-only account role assignment for the current deployment workspace."""
    actor = get_user(request.cookies.get("ct_auth_session"))
    if not actor or actor.get("role") not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Only an organization owner or admin can assign account roles.")
    if actor.get("role") == "admin" and payload.role not in {"viewer", "analyst", "remove"}:
        raise HTTPException(status_code=403, detail="Admins can add, remove, or change analyst/viewer access. Only the owner can assign admins.")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", payload.email) or len(payload.email) > 254:
        raise HTTPException(status_code=400, detail="Enter a valid account email.")
    try:
        changed = set_user_role(payload.email, payload.role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not changed:
        raise HTTPException(status_code=404, detail="That account has not signed in yet.")
    notify_owner_for_request(request, "Workspace account access changed")
    return {"success": True}


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response) -> Dict[str, Any]:
    """Revoke this browser session and clear its cookies."""
    notify_owner_for_request(request, "User signed out")
    logout_auth_session(request.cookies.get("ct_auth_session"))
    response.delete_cookie("ct_auth_session", path="/", httponly=True, secure=request.url.scheme == "https", samesite="lax")
    response.delete_cookie("ct_session_id", path="/", httponly=True, secure=request.url.scheme == "https", samesite="lax")
    return {"success": True}


@app.post("/api/auth/public-demo")
def auth_public_demo(request: Request, response: Response) -> Dict[str, Any]:
    """Issue an expiring sandbox workspace backed by synthetic sample data."""
    source_ip = request.headers.get("x-forwarded-for", "")
    if source_ip:
        source_ip = source_ip.split(",", 1)[0].strip()
    else:
        source_ip = request.client.host if request.client else "unknown"
    try:
        token, workspace_id = create_public_demo(source_ip)
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    SESSION_STORE[workspace_id] = SessionManager(load_demo_dataset(), filename="synthetic_quality_issues.csv")
    persist_session(workspace_id)
    is_https = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(
        key="ct_public_demo", value=token, httponly=True, secure=is_https,
        samesite="lax", max_age=8 * 60 * 60, path="/",
    )
    response.set_cookie(
        key="ct_session_id", value=workspace_id, httponly=True, secure=is_https,
        samesite="lax", max_age=8 * 60 * 60, path="/",
    )
    return {"success": True, "message": "Sample evaluation workspace opened."}


@app.post("/api/dataset/upload")
async def upload_csv(request: Request, file: UploadFile = File(...)) -> Dict[str, Any]:
    demo_mode = os.environ.get("CLEARTRACE_DEMO_MODE", "true").lower() in ("true", "1")
    if not demo_mode and not check_access_authorization(request):
        raise HTTPException(
            status_code=401,
            detail="Sign in with an email verification code to continue.",
        )

    fname = file.filename or "uploaded.csv"
    fname_lower = fname.lower()
    if fname_lower.endswith(".xls"):
        raise HTTPException(
            status_code=400,
            detail="Legacy Excel 97-2003 format (.xls) is not supported. Please convert and upload as modern Excel (.xlsx) or CSV (.csv).",
        )
    allowed_exts = (".csv", ".tsv", ".xlsx", ".pdf")
    if not fname_lower.endswith(allowed_exts):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format. Supported formats: CSV, TSV, XLSX, PDF.",
        )

    # Stream in chunks with an upper bound to prevent memory exhaustion DoS
    max_mb = int(os.environ.get("CLEARTRACE_MAX_UPLOAD_MB", "10"))
    MAX_FILE_BYTES = max_mb * 1024 * 1024
    raw_buffer = bytearray()
    while chunk := await file.read(64 * 1024):
        raw_buffer.extend(chunk)
        if len(raw_buffer) > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"Upload payload exceeds maximum allowable limit of {max_mb} MB.",
            )

    try:
        contents = bytes(raw_buffer)
        fname = file.filename or "uploaded.csv"
        df, meta = parse_document_bytes(contents, filename=fname)
        token = current_session_token.get()
        sm = SessionManager(
            df,
            filename=fname,
            provenance_map=meta.get("provenance_map"),
            document_format=meta.get("format", "csv"),
            warnings=meta.get("warnings"),
        )
        SESSION_STORE[token] = sm
        persist_session(token, sm)

        findings, metrics = scan_dataset(df)
        score = calculate_quality_score(df, findings)
        math_findings = sm.get_math_findings()
        notify_owner_for_request(request, "Dataset uploaded to workspace")
        return {
            "success": True,
            "filename": fname,
            "format": meta.get("format", "csv"),
            "metadata": meta,
            "quality_score": score.overall_score,
            "grade": score.grade,
            "revision": sm.dataset_revision,
            "math_issues_count": len(math_findings),
            "warnings": meta.get("warnings", []),
        }
    except IngestionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/dataset/demo")
def load_demo(request: Request) -> Dict[str, Any]:
    df = load_demo_dataset()
    token = current_session_token.get()
    sm = SessionManager(df, filename="synthetic_quality_issues.csv")
    SESSION_STORE[token] = sm
    persist_session(token, sm)

    findings, metrics = scan_dataset(df)
    score = calculate_quality_score(df, findings)
    notify_owner_for_request(request, "Sample dataset loaded")
    return {
        "success": True,
        "filename": sm.filename,
        "format": "csv",
        "total_rows": len(df),
        "total_columns": len(df.columns),
        "quality_score": score.overall_score,
        "grade": score.grade,
        "revision": sm.dataset_revision,
    }


@app.post("/api/dataset/math-demo")
def load_math_demo(req: MathDemoRequest, request: Request) -> Dict[str, Any]:
    try:
        df, meta = load_math_demo_dataset(fmt=req.format)
    except IngestionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    token = current_session_token.get()
    sm = SessionManager(
        df,
        filename=meta["filename"],
        provenance_map=meta.get("provenance_map"),
        document_format=meta.get("format", req.format),
        warnings=meta.get("warnings"),
    )
    SESSION_STORE[token] = sm
    persist_session(token, sm)

    findings, metrics = scan_dataset(df)
    score = calculate_quality_score(df, findings)
    math_findings = sm.get_math_findings()
    notify_owner_for_request(request, "Sample financial dataset loaded")
    return {
        "success": True,
        "filename": sm.filename,
        "format": meta.get("format", req.format),
        "total_rows": len(df),
        "total_columns": len(df.columns),
        "quality_score": score.overall_score,
        "grade": score.grade,
        "revision": sm.dataset_revision,
        "math_issues_count": len(math_findings),
        "warnings": meta.get("warnings", []),
    }


@app.get("/api/dataset/summary")
def get_dataset_summary() -> Dict[str, Any]:
    sm = get_session()
    df = sm.working_df
    findings, metrics = scan_dataset(df)
    score = calculate_quality_score(df, findings)
    math_findings = sm.get_math_findings()

    preview_records = df.head(100).to_dict(orient="records")
    return {
        "filename": sm.filename,
        "format": sm.document_format,
        "revision": sm.dataset_revision,
        "rows": len(df),
        "columns": list(df.columns),
        "column_types": {col: str(df[col].dtype) for col in df.columns},
        "preview": preview_records,
        "warnings": sm.warnings,
        "metrics": {
            "total_rows": metrics.total_rows,
            "total_columns": metrics.total_columns,
            "total_cells": metrics.total_cells,
            "completeness_pct": metrics.completeness_pct,
            "missing_cells": metrics.missing_cells,
            "duplicate_rows": metrics.duplicate_rows,
            "format_violations": metrics.format_violations,
            "review_count": metrics.review_count,
            "math_issues": len(math_findings),
        },
        "quality_score": score.overall_score,
        "grade": score.grade,
    }


@app.get("/api/quality/score")
def get_quality_score() -> Dict[str, Any]:
    sm = get_session()
    findings, _ = scan_dataset(sm.working_df)
    report = calculate_quality_score(sm.working_df, findings)

    # Dedicated Mathematical Integrity Dimension
    math_findings = sm.get_math_findings()
    total_rows = max(1, len(sm.working_df))
    math_integrity_score = round(max(0.0, 1.0 - (len(math_findings) / total_rows)) * 100.0, 1)
    has_math = len(math_findings) > 0 or bool(getattr(sm, "custom_math_rules", None))
    composite_score = round(0.70 * report.overall_score + 0.30 * math_integrity_score, 1) if has_math else report.overall_score

    return {
        "overall_score": report.overall_score,
        "grade": report.grade,
        "summary": report.summary,
        "math_integrity_score": math_integrity_score,
        "math_issues_count": len(math_findings),
        "composite_score": composite_score,
        "components": [
            {
                "name": c.name,
                "weight_pct": c.weight_pct,
                "raw_score": c.raw_score,
                "weighted_score": c.weighted_score,
                "deductions": c.deductions,
                "explanation": c.explanation,
            }
            for c in report.components
        ],
    }


@app.get("/api/quality/findings")
def get_findings() -> List[Dict[str, Any]]:
    sm = get_session()
    findings, _ = scan_dataset(sm.working_df)
    return [
        {
            "id": f.id,
            "rule_id": f.rule_id,
            "kind": f.kind,
            "column": f.column,
            "affected_count": f.affected_count,
            "affected_row_indices": f.affected_row_indices,
            "example": f.example,
            "explanation": f.explanation,
            "recommendation": f.recommendation,
            "risk": f.risk,
            "action": f.action,
        }
        for f in findings
    ]


@app.get("/api/repair/proposals")
def get_proposals() -> List[Dict[str, Any]]:
    sm = get_session()
    findings, _ = scan_dataset(sm.working_df)
    ranked = rank_proposals(findings)

    results = []
    # 1. Standard scan proposals
    for finding, priority_score, priority_reason in ranked:
        if finding.id in getattr(sm, "rejected_findings", set()):
            continue
        prop = generate_proposal(finding, sm.working_df)
        sim = simulate_impact(sm.working_df, finding)
        results.append({
            "proposal_id": prop.proposal_id,
            "finding_id": finding.id,
            "rule_id": prop.rule_id,
            "column": prop.column,
            "kind": finding.kind,
            "risk": prop.risk,
            "priority_score": priority_score,
            "priority_reason": priority_reason,
            "affected_records": len(prop.target_rows),
            "before_summary": prop.before_summary,
            "after_summary": prop.after_summary,
            "diff_sample": [
                {
                    "row": d.row_idx,
                    "column": d.column,
                    "before": str(d.before),
                    "after": str(d.after),
                }
                for d in prop.diff_sample
            ],
            "impact_simulation": {
                "cells_affected": sim.cells_affected,
                "rows_affected": sim.rows_affected,
                "data_loss_risk": sim.data_loss_risk,
                "resolved_issue": sim.resolved_issue_description,
                "side_effects": sim.side_effects,
            },
        })

    # 2. Mathematical proposals (e.g. formula discrepancies, missing totals)
    math_findings = sm.get_math_findings()
    math_pairs = convert_math_findings_to_proposals(math_findings, sm.working_df)
    for m_finding, m_prop in math_pairs:
        if m_finding.id in getattr(sm, "rejected_findings", set()):
            continue
        results.append({
            "proposal_id": m_prop.proposal_id,
            "finding_id": m_finding.id,
            "rule_id": m_prop.rule_id,
            "column": m_prop.column,
            "kind": m_finding.kind,
            "risk": m_prop.risk,
            "priority_score": 95.0,
            "priority_reason": f"Direct mathematical error: {m_finding.example}",
            "affected_records": len(m_prop.target_rows),
            "before_summary": m_prop.before_summary,
            "after_summary": m_prop.after_summary,
            "diff_sample": [
                {
                    "row": d.row_idx,
                    "column": d.column,
                    "before": str(d.before),
                    "after": str(d.after),
                }
                for d in m_prop.diff_sample
            ],
            "impact_simulation": {
                "cells_affected": len(m_prop.diff_sample),
                "rows_affected": len(m_prop.target_rows),
                "data_loss_risk": "Low (Verified arithmetic recalculation)",
                "resolved_issue": m_finding.explanation,
                "side_effects": "Replaces reported total with exact calculated decimal value.",
            },
        })

    return results


@app.post("/api/repair/apply")
def apply_repair_proposal(req: ApplyRequest, request: Request) -> Dict[str, Any]:
    sm = get_session()
    # Concurrency guard: check revision first
    if req.expected_revision != sm.dataset_revision:
        raise HTTPException(
            status_code=409,
            detail=f"Stale revision: Expected {req.expected_revision}, but current is {sm.dataset_revision}."
        )

    findings, _ = scan_dataset(sm.working_df)
    finding = next((f for f in findings if f.id == req.finding_id), None)
    prop = None

    if not finding:
        # Check if finding is a math finding proposal
        math_findings = sm.get_math_findings()
        math_pairs = convert_math_findings_to_proposals(math_findings, sm.working_df)
        for std_f, std_p in math_pairs:
            if std_f.id == req.finding_id:
                finding = std_f
                prop = std_p
                break

    if not finding or not finding.action:
        raise HTTPException(status_code=404, detail="Proposal not found or not actionable.")

    if prop is None:
        prop = generate_proposal(finding, sm.working_df)

    try:
        event = sm.apply_proposal(prop, expected_revision=req.expected_revision)
        persist_session(current_session_token.get(), sm)
        notify_owner_for_request(request, "Repair approved and applied")
        return {
            "success": True,
            "event_id": event.event_id,
            "revision": sm.dataset_revision,
            "items_changed": event.items_changed,
            "detail": event.reason,
        }
    except StaleRevisionError as err:
        raise HTTPException(status_code=409, detail=str(err))


@app.post("/api/repair/reject-notice")
def reject_repair_notice(req: RejectRepairRequest, request: Request) -> Dict[str, Any]:
    """Persist a user's rejection so it remains dismissed across refreshes."""
    if not req.finding_id or len(req.finding_id) > 200:
        raise HTTPException(status_code=400, detail="Invalid repair identifier.")
    sm = get_session()
    findings, _ = scan_dataset(sm.working_df)
    valid_ids = {finding.id for finding in findings}
    valid_ids.update(f.id for f in sm.get_math_findings())
    if req.finding_id not in valid_ids:
        raise HTTPException(status_code=404, detail="That finding is no longer available.")
    sm.rejected_findings.add(req.finding_id)
    persist_session(current_session_token.get(), sm)
    notify_owner_for_request(request, "Repair proposal rejected")
    return {"success": True}


@app.post("/api/repair/batch-apply")
def batch_apply_repairs(req: BatchApplyRequest, request: Request) -> Dict[str, Any]:
    sm = get_session()
    if req.expected_revision != sm.dataset_revision:
        raise HTTPException(
            status_code=409,
            detail=f"Stale revision: Expected {req.expected_revision}, but current is {sm.dataset_revision}."
        )

    applied_events = []
    total_changed = 0
    for fid in req.finding_ids:
        findings, _ = scan_dataset(sm.working_df)
        finding = next((f for f in findings if f.id == fid and f.action), None)
        if not finding:
            continue
        prop = generate_proposal(finding, sm.working_df)
        event = sm.apply_proposal(prop, expected_revision=sm.dataset_revision)
        applied_events.append(event.event_id)
        total_changed += event.items_changed

    persist_session(current_session_token.get(), sm)
    if applied_events:
        notify_owner_for_request(request, "Batch of repairs approved and applied")
    return {
        "success": True,
        "applied_events": applied_events,
        "total_items_changed": total_changed,
        "final_revision": sm.dataset_revision,
    }


@app.post("/api/audit/undo")
def undo_action(request: Request) -> Dict[str, Any]:
    sm = get_session()
    event = sm.undo_last_action()
    if not event:
        raise HTTPException(status_code=400, detail="Undo stack is empty.")
    persist_session(current_session_token.get(), sm)
    notify_owner_for_request(request, "Workspace change undone")
    return {
        "success": True,
        "event_id": event.event_id,
        "undone_event": event.undo_of,
        "new_revision": sm.dataset_revision,
    }


@app.post("/api/audit/reset")
def reset_to_baseline(request: Request) -> Dict[str, Any]:
    sm = get_session()
    event = sm.reset_to_original()
    persist_session(current_session_token.get(), sm)
    notify_owner_for_request(request, "Workspace reset to original dataset")
    return {
        "success": True,
        "event_id": event.event_id,
        "new_revision": sm.dataset_revision,
        "rows": len(sm.working_df),
    }


@app.get("/api/audit/events")
def get_audit_events() -> List[Dict[str, Any]]:
    sm = get_session()
    return [
        {
            "event_id": e.event_id,
            "timestamp_utc": e.timestamp_utc,
            "rev_before": e.dataset_revision_before,
            "rev_after": e.dataset_revision_after,
            "actor": e.actor,
            "decision": e.decision,
            "rule_id": e.rule_id,
            "target_columns": e.target_columns,
            "items_changed": e.items_changed,
            "before_summary": e.before_summary,
            "after_summary": e.after_summary,
            "reason": e.reason,
            "undo_of": e.undo_of,
        }
        for e in sm.audit_events
    ]


@app.get("/api/timemachine/timeline")
def get_timeline() -> List[Dict[str, Any]]:
    sm = get_session()
    return sm.time_machine.list_timeline()


@app.post("/api/timemachine/compare")
def compare_snapshots(req: CompareRequest) -> Dict[str, Any]:
    sm = get_session()
    comp = sm.time_machine.compare_revisions(req.rev_from, req.rev_to)
    if not comp:
        raise HTTPException(status_code=404, detail="One or both revisions not found.")
    return {
        "from_revision": comp.from_revision,
        "to_revision": comp.to_revision,
        "rows_before": comp.rows_before,
        "rows_after": comp.rows_after,
        "net_row_change": comp.net_row_change,
        "columns_changed": comp.columns_changed,
        "sample_diffs": comp.sample_diffs,
    }


@app.post("/api/timemachine/restore")
def restore_snapshot(req: RestoreRequest, request: Request) -> Dict[str, Any]:
    sm = get_session()
    try:
        event = sm.restore_to_revision(req.target_revision)
        persist_session(current_session_token.get(), sm)
        notify_owner_for_request(request, "Workspace revision restored")
        return {
            "success": True,
            "event_id": event.event_id,
            "restored_to_revision": req.target_revision,
            "current_revision": sm.dataset_revision,
            "rows": len(sm.working_df),
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/passport")
def get_passport() -> Dict[str, Any]:
    sm = get_session()
    findings, _ = scan_dataset(sm.working_df)
    score_report = calculate_quality_score(sm.working_df, findings)
    passport = generate_data_passport(
        original_df=sm.original_df,
        working_df=sm.working_df,
        filename=sm.filename,
        score_report=score_report,
        findings=findings,
        audit_events=sm.audit_events,
    )
    return {
        "passport_id": passport.passport_id,
        "issued_at_utc": passport.issued_at_utc,
        "filename": passport.filename,
        "original_sha256": passport.original_sha256,
        "cleaned_sha256": passport.cleaned_sha256,
        "total_rows": passport.total_rows,
        "total_columns": passport.total_columns,
        "quality_score": passport.quality_score,
        "grade": passport.grade,
        "completeness_pct": passport.completeness_pct,
        "repairs_applied_count": passport.repairs_applied_count,
        "unresolved_warnings_count": passport.unresolved_warnings_count,
        "audit_events_count": passport.audit_events_count,
        "score_breakdown": passport.score_breakdown,
        "unresolved_findings": passport.unresolved_findings,
        "integrity_signature": passport.integrity_signature,
    }


# ── Mathematical Error Intelligence ──────────────────────────────────────────

@app.get("/api/math/findings")
def get_math_findings_endpoint(tolerance: float = Query(default=0.01)) -> List[Dict[str, Any]]:
    sm = get_session()
    mf_list = sm.get_math_findings(tolerance_val=tolerance)
    return [
        {
            "id": f.id,
            "source_ref": f.source_ref,
            "invoice_id": f.invoice_id,
            "rule_id": f.rule_id,
            "severity": f.severity,
            "field": f.field,
            "message": f.message,
            "observed": f.observed,
            "expected": f.expected,
            "deviation": f.deviation,
            "calculation_steps": f.calculation_steps,
            "row_idx": f.row_idx,
            "action": f.action,
            "proposed_value": f.proposed_value,
        }
        for f in mf_list
    ]


@app.post("/api/math/validate")
def validate_math_endpoint(req: ValidateMathRequest) -> Dict[str, Any]:
    sm = get_session()
    if req.custom_rules:
        new_rules = []
        for r_dict in req.custom_rules:
            new_rules.append(MathRuleConfig(**r_dict))
        sm.custom_math_rules = new_rules
        persist_session(current_session_token.get(), sm)

    mf_list = sm.get_math_findings(tolerance_val=req.tolerance)
    mismatches = [f for f in mf_list if f.rule_id in ("MATH_MISMATCH", "FORMULA_MISMATCH", "SUBTOTAL_MISMATCH", "PERCENTAGE_MISMATCH", "PERCENTAGE_CHANGE_MISMATCH")]
    invalid_nums = [f for f in mf_list if f.rule_id == "INVALID_NUMBER"]
    negative_violations = [f for f in mf_list if f.rule_id == "NEGATIVE_NOT_ALLOWED"]
    missing_totals = [f for f in mf_list if f.rule_id in ("MISSING_TOTAL", "MISSING_CALCULATED_VALUE")]
    discount_violations = [f for f in mf_list if f.rule_id in ("DISCOUNT_EXCEEDS_SUBTOTAL", "CONSTRAINT_VIOLATION")]
    outliers = [f for f in mf_list if f.rule_id == "OUTLIER_CANDIDATE"]

    return {
        "success": True,
        "tolerance": req.tolerance,
        "total_math_issues": len(mf_list),
        "summary": {
            "math_mismatches": len(mismatches),
            "invalid_numbers": len(invalid_nums),
            "negative_not_allowed": len(negative_violations),
            "missing_totals": len(missing_totals),
            "discount_exceeds_subtotal": len(discount_violations),
            "outliers": len(outliers),
        },
        "findings": [
            {
                "id": f.id,
                "source_ref": f.source_ref,
                "invoice_id": f.invoice_id,
                "rule_id": f.rule_id,
                "severity": f.severity,
                "field": f.field,
                "message": f.message,
                "observed": f.observed,
                "expected": f.expected,
                "deviation": f.deviation,
                "calculation_steps": f.calculation_steps,
                "proposed_value": f.proposed_value,
            }
            for f in mf_list
        ],
    }


@app.get("/api/math/rules")
def get_math_rules() -> List[Dict[str, Any]]:
    sm = get_session()
    return [
        {
            "rule_id": r.rule_id,
            "rule_type": r.rule_type,
            "target_column": r.target_column,
            "expression": r.expression,
            "addend_columns": r.addend_columns,
            "part_column": r.part_column,
            "total_column": r.total_column,
            "old_column": r.old_column,
            "new_column": r.new_column,
            "constraint_type": r.constraint_type,
            "constraint_value": r.constraint_value,
            "tolerance": r.tolerance,
            "decimal_places": r.decimal_places,
            "rounding_mode": r.rounding_mode,
            "severity": r.severity,
            "description": r.description,
        }
        for r in getattr(sm, "custom_math_rules", [])
    ]


@app.post("/api/math/rules")
def add_or_update_math_rule(req: MathRuleRequest, request: Request) -> Dict[str, Any]:
    sm = get_session()
    existing = [r for r in getattr(sm, "custom_math_rules", []) if r.rule_id != req.rule_id]
    new_rule = MathRuleConfig(
        rule_id=req.rule_id,
        rule_type=req.rule_type,
        target_column=req.target_column,
        expression=req.expression,
        addend_columns=req.addend_columns,
        part_column=req.part_column,
        total_column=req.total_column,
        old_column=req.old_column,
        new_column=req.new_column,
        constraint_type=req.constraint_type,
        constraint_value=req.constraint_value,
        tolerance=req.tolerance,
        decimal_places=req.decimal_places,
        rounding_mode=req.rounding_mode,
        severity=req.severity,
        description=req.description or f"Rule {req.rule_id} ({req.rule_type})",
    )
    existing.append(new_rule)
    sm.custom_math_rules = existing
    persist_session(current_session_token.get(), sm)
    notify_owner_for_request(request, "Workspace validation rule added or updated")
    findings = sm.get_math_findings()
    return {
        "success": True,
        "rule_id": req.rule_id,
        "total_rules": len(sm.custom_math_rules),
        "total_math_issues": len(findings),
    }


@app.delete("/api/math/rules/{rule_id}")
def delete_math_rule(rule_id: str, request: Request) -> Dict[str, Any]:
    sm = get_session()
    sm.custom_math_rules = [r for r in getattr(sm, "custom_math_rules", []) if r.rule_id != rule_id]
    persist_session(current_session_token.get(), sm)
    notify_owner_for_request(request, "Workspace validation rule removed")
    findings = sm.get_math_findings()
    return {
        "success": True,
        "deleted_rule_id": rule_id,
        "total_rules": len(sm.custom_math_rules),
        "total_math_issues": len(findings),
    }


# ── RAG Knowledge Assistant & Retrieval ───────────────────────────────────────

@app.get("/api/rag/status")
def rag_status() -> Dict[str, Any]:
    sm = get_session()
    llm_info = get_llm_status()
    findings, _ = scan_dataset(sm.working_df)
    idx = sm.get_evidence_index(quality_findings=findings)
    return {
        "status": "ready",
        "indexed_passages": len(idx.passages),
        "dataset_name": sm.filename,
        "format": sm.document_format,
        "llm_provider": llm_info.get("provider"),
        "llm_model": llm_info.get("model"),
        "llm_available": llm_info.get("available"),
        "llm_status_message": llm_info.get("message"),
    }


@app.post("/api/rag/search")
def rag_search(req: RAGSearchRequest) -> Dict[str, Any]:
    sm = get_session()
    findings, _ = scan_dataset(sm.working_df)
    idx = sm.get_evidence_index(quality_findings=findings)
    results = idx.search(req.query, limit=req.limit)
    return {
        "query": req.query,
        "total_results": len(results),
        "results": [
            {
                "score": r[0],
                "ref": r[1].ref,
                "title": r[1].title,
                "text": r[1].text,
                "source_type": r[1].source_type,
            }
            for r in results
        ],
    }


@app.post("/api/rag/ask")
def rag_ask(req: RAGAskRequest) -> Dict[str, Any]:
    sm = get_session()
    findings, _ = scan_dataset(sm.working_df)
    idx = sm.get_evidence_index(quality_findings=findings)
    answer = ask_knowledge_assistant(req.question, idx, limit=req.limit)
    return {
        "question": req.question,
        "answer": answer.answer,
        "references": answer.references,
        "provider": answer.provider,
        "status": answer.status,
        "evidence_matches": answer.evidence_matches,
    }


# ── File Download Exports ───────────────────────────────────────────────────

@app.get("/api/export/cleaned")
def download_cleaned_csv(request: Request):
    sm = get_session()
    csv_bytes = export_cleaned_csv(sm.working_df, escape_formulas=True)
    notify_owner_for_request(request, "Cleaned dataset exported")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="cleartrace_cleaned_{sm.filename}"'},
    )


@app.get("/api/export/findings")
def download_findings(request: Request):
    sm = get_session()
    findings, _ = scan_dataset(sm.working_df)
    csv_bytes = export_findings_report(findings)
    notify_owner_for_request(request, "Quality findings exported")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="cleartrace_findings_{sm.filename}"'},
    )


@app.get("/api/export/audit")
def download_audit(request: Request):
    sm = get_session()
    csv_bytes = export_audit_log(sm.audit_events)
    notify_owner_for_request(request, "Audit history exported")
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="cleartrace_audit_{sm.filename}"'},
    )


@app.get("/api/export/passport")
def download_passport_json(request: Request):
    sm = get_session()
    findings, _ = scan_dataset(sm.working_df)
    score = calculate_quality_score(sm.working_df, findings)
    passport = generate_data_passport(
        original_df=sm.original_df,
        working_df=sm.working_df,
        filename=sm.filename,
        score_report=score,
        findings=findings,
        audit_events=sm.audit_events,
    )
    passport_dict = {
        "passport_id": passport.passport_id,
        "issued_at_utc": passport.issued_at_utc,
        "filename": passport.filename,
        "original_sha256": passport.original_sha256,
        "cleaned_sha256": passport.cleaned_sha256,
        "quality_score": passport.quality_score,
        "grade": passport.grade,
        "completeness_pct": passport.completeness_pct,
        "repairs_applied_count": passport.repairs_applied_count,
        "unresolved_warnings_count": passport.unresolved_warnings_count,
        "score_breakdown": passport.score_breakdown,
        "unresolved_findings": passport.unresolved_findings,
        "integrity_signature": passport.integrity_signature,
    }
    notify_owner_for_request(request, "Data passport exported")
    return Response(
        content=json.dumps(passport_dict, indent=2).encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="cleartrace_passport_{passport.passport_id}.json"'},
    )


@app.get("/api/comparison/summary")
def get_comparison_summary() -> Dict[str, Any]:
    """Feature C: Compares original baseline (Rev 1) with current working state (Rev N)."""
    sm = get_session()
    orig_findings, _ = scan_dataset(sm.original_df)
    orig_score = calculate_quality_score(sm.original_df, orig_findings)

    curr_findings, _ = scan_dataset(sm.working_df)
    curr_score = calculate_quality_score(sm.working_df, curr_findings)

    orig_math = sm.get_math_findings(df=sm.original_df)
    curr_math = sm.get_math_findings(df=sm.working_df)

    resolved_count = max(0, len(orig_findings) - len(curr_findings))
    resolved_math = max(0, len(orig_math) - len(curr_math))

    total_orig_rows = max(1, len(sm.original_df))
    total_curr_rows = max(1, len(sm.working_df))
    math_score_before = round(max(0.0, 1.0 - (len(orig_math) / total_orig_rows)) * 100.0, 1)
    math_score_after = round(max(0.0, 1.0 - (len(curr_math) / total_curr_rows)) * 100.0, 1)
    math_score_delta = round(math_score_after - math_score_before, 2)

    has_math = len(orig_math) > 0 or len(curr_math) > 0 or bool(getattr(sm, "custom_math_rules", None))
    if has_math:
        composite_before = round(0.70 * orig_score.overall_score + 0.30 * math_score_before, 1)
        composite_after = round(0.70 * curr_score.overall_score + 0.30 * math_score_after, 1)
    else:
        composite_before = orig_score.overall_score
        composite_after = curr_score.overall_score
    composite_delta = round(composite_after - composite_before, 2)

    applied_repairs = [e for e in sm.audit_events if e.decision in ("approved", "applied")]
    repair_breakdown_dict = {}
    for e in applied_repairs:
        rule_key = e.rule_id or "MUTATION"
        repair_breakdown_dict[rule_key] = repair_breakdown_dict.get(rule_key, 0) + 1
    repairs_breakdown = [{"rule_id": k, "count": v} for k, v in repair_breakdown_dict.items()]

    return {
        "success": True,
        "filename": sm.filename,
        "revision_baseline": 1,
        "revision_current": sm.dataset_revision,
        "score_before": orig_score.overall_score,
        "score_after": curr_score.overall_score,
        "score_baseline": orig_score.overall_score,
        "score_current": curr_score.overall_score,
        "score_delta": round(curr_score.overall_score - orig_score.overall_score, 2),
        "math_score_baseline": math_score_before,
        "math_score_current": math_score_after,
        "math_score_before": math_score_before,
        "math_score_after": math_score_after,
        "math_score_delta": math_score_delta,
        "composite_score_baseline": composite_before,
        "composite_score_current": composite_after,
        "composite_score_before": composite_before,
        "composite_score_after": composite_after,
        "composite_score_delta": composite_delta,
        "grade_before": orig_score.grade,
        "grade_after": curr_score.grade,
        "grade_baseline": orig_score.grade,
        "grade_current": curr_score.grade,
        "total_repairs_applied": len(applied_repairs),
        "repairs_breakdown": repairs_breakdown,
        "initial_issues_count": len(orig_findings),
        "current_issues_count": len(curr_findings),
        "remaining_issues_count": len(curr_findings),
        "resolved_issues_count": resolved_count,
        "initial_math_issues_count": len(orig_math),
        "current_math_issues_count": len(curr_math),
        "resolved_math_issues_count": resolved_math,
        "components_before": [
            {"name": c.name, "score": c.raw_score, "weight": c.weight_pct} for c in orig_score.components
        ],
        "components_after": [
            {"name": c.name, "score": c.raw_score, "weight": c.weight_pct} for c in curr_score.components
        ],
        "recent_audit_events": [
            {
                "event_id": e.event_id,
                "timestamp_utc": e.timestamp_utc,
                "decision": e.decision,
                "items_changed": e.items_changed,
                "reason": e.reason,
            }
            for e in sm.audit_events[-5:]
        ],
    }


@app.get("/api/export/report")
def download_executive_report(request: Request, format: str = Query("markdown", pattern="^(markdown|json|html)$"), download: bool = False):
    """Feature D: Generates and exports the comprehensive data quality assessment report."""
    sm = get_session()
    findings, _ = scan_dataset(sm.working_df)
    score_report = calculate_quality_score(sm.working_df, findings)
    passport = generate_data_passport(
        original_df=sm.original_df,
        working_df=sm.working_df,
        filename=sm.filename,
        score_report=score_report,
        findings=findings,
        audit_events=sm.audit_events,
    )
    math_findings = sm.get_math_findings()

    score_dict = {
        "overall_score": score_report.overall_score,
        "grade": score_report.grade,
        "components": [
            {
                "name": c.name,
                "weight": c.weight_pct,
                "raw_score": c.raw_score,
                "weighted_contribution": c.weighted_score,
            }
            for c in score_report.components
        ],
    }

    report_md = export_comprehensive_report(
        filename=sm.filename,
        raw_sha256=passport.original_sha256,
        cleaned_sha256=passport.cleaned_sha256,
        working_df=sm.working_df,
        score_data=score_dict,
        findings=findings,
        math_findings=math_findings,
        audit_events=sm.audit_events,
        passport_id=passport.passport_id,
        revision=sm.dataset_revision,
    )
    notify_owner_for_request(request, "Executive quality report exported")

    if format == "json":
        return {
            "success": True,
            "filename": sm.filename,
            "passport_id": passport.passport_id,
            "report_markdown": report_md,
            "score": score_dict,
            "math_issues": len(math_findings),
            "quality_issues": len(findings),
            "audit_events_count": len(sm.audit_events),
        }

    headers = {}
    if download:
        safe_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', sm.filename)
        headers["Content-Disposition"] = f'attachment; filename="cleartrace_report_{safe_name}.md"'

    return Response(content=report_md, media_type="text/markdown", headers=headers)


# Static file serving is mounted at bottom after frontend directory is ready


# ── Static Files & SPA Mount ────────────────────────────────────────────────
import os
from fastapi.responses import FileResponse

static_dir = os.path.join(os.path.dirname(__file__), 'static')
if os.path.exists(static_dir):
    app.mount('/static', StaticFiles(directory=static_dir), name='static')

@app.get('/', response_class=FileResponse)
def serve_spa():
    return FileResponse(os.path.join(static_dir, 'index.html'))

@app.get('/manifest.json', response_class=FileResponse)
def serve_manifest():
    return FileResponse(
        os.path.join(static_dir, 'manifest.json'),
        media_type='application/manifest+json',
        headers={'Cache-Control': 'no-cache, must-revalidate'}
    )

@app.get('/sw.js', response_class=FileResponse)
def serve_sw():
    return FileResponse(
        os.path.join(static_dir, 'sw.js'),
        media_type='application/javascript',
        headers={
            'Service-Worker-Allowed': '/',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache',
            'Expires': '0',
        }
    )

@app.get('/apple-touch-icon.png', response_class=FileResponse)
def serve_apple_touch_icon():
    return FileResponse(os.path.join(static_dir, 'apple-touch-icon.png'), media_type='image/png')

@app.get('/favicon.ico', response_class=FileResponse)
def serve_favicon():
    return FileResponse(os.path.join(static_dir, 'favicon-32.png'), media_type='image/png')


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")  # nosec: B104
    print(f"[*] ClearTrace Production Server starting on {host}:{port}")
    uvicorn.run("server:app", host=host, port=port, workers=1, log_level="info")


