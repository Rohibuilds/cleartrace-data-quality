"""Email one-time-code authentication for ClearTrace's browser workspace."""

from __future__ import annotations

import hashlib
import hmac
import base64
import logging
import os
import secrets
import smtplib
import sqlite3
import ssl
import time
import json
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from cryptography.fernet import Fernet

from cleartrace.persistence import get_storage_dir, delete_encrypted_session

logger = logging.getLogger("cleartrace.auth")
OTP_TTL_SECONDS = 600
OTP_COOLDOWN_SECONDS = 60
OTP_MAX_ATTEMPTS = 5
SESSION_TTL_SECONDS = 60 * 60 * 24 * 30
PUBLIC_DEMO_TTL_SECONDS = 60 * 60 * 8


def _db_path() -> Path:
    return get_storage_dir() / "auth.sqlite3"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(path, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=10000")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_key TEXT PRIMARY KEY,
            email_ciphertext TEXT NOT NULL,
            workspace_id TEXT NOT NULL UNIQUE,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS otp_challenges (
            user_key TEXT PRIMARY KEY,
            code_hash TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            sent_at INTEGER NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS otp_requests (
            user_key TEXT NOT NULL,
            ip_hash TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS otp_requests_ip_time ON otp_requests(ip_hash, created_at);
        CREATE TABLE IF NOT EXISTS auth_sessions (
            token_hash TEXT PRIMARY KEY,
            user_key TEXT NOT NULL REFERENCES users(user_key) ON DELETE CASCADE,
            expires_at INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS auth_sessions_expiry ON auth_sessions(expires_at);
        CREATE TABLE IF NOT EXISTS public_demo_sessions (
            token_hash TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            expires_at INTEGER NOT NULL
        );
    """)
    columns = {row[1] for row in db.execute("PRAGMA table_info(users)")}
    if "role" not in columns:
        db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'analyst'")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS organizations (
            organization_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL UNIQUE,
            owner_user_key TEXT NOT NULL UNIQUE,
            created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS organization_members (
            user_key TEXT PRIMARY KEY,
            organization_id TEXT NOT NULL,
            role TEXT NOT NULL,
            joined_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS login_events (
            user_key TEXT NOT NULL, ip_hash TEXT NOT NULL, created_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS oauth_states (
            state_hash TEXT PRIMARY KEY, expires_at INTEGER NOT NULL
        );
    """)
    return db


def _auth_key() -> bytes:
    """Load/create a stable private key used to hash short OTPs and source IPs."""
    env_key = os.environ.get("CLEARTRACE_AUTH_SECRET") or os.environ.get("CLEARTRACE_MASTER_KEY")
    if env_key:
        if len(env_key.encode("utf-8")) < 32:
            raise RuntimeError("CLEARTRACE_AUTH_SECRET must contain at least 32 bytes; use a randomly generated secret.")
        return hashlib.sha256(env_key.encode("utf-8")).digest()
    path = get_storage_dir() / "keys" / "auth.key"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        key = path.read_bytes()
        if len(key) != 32:
            raise RuntimeError("The ClearTrace auth key file is invalid. Restore it from the persistent volume backup.")
        return key
    key = secrets.token_bytes(32)
    with os.fdopen(fd, "wb") as stream:
        stream.write(key)
        stream.flush()
        os.fsync(stream.fileno())
    return key


def _digest(value: str, purpose: bytes) -> str:
    return hmac.new(_auth_key(), purpose + value.encode("utf-8"), hashlib.sha256).hexdigest()


def _email_key(email: str) -> str:
    return _digest(email, b"email:")


def _encrypt_email(email: str) -> str:
    key = base64.urlsafe_b64encode(hashlib.sha256(b"cleartrace-email-v1:" + _auth_key()).digest())
    return Fernet(key).encrypt(email.encode("utf-8")).decode("ascii")


def _decrypt_email(ciphertext: str) -> str:
    key = base64.urlsafe_b64encode(hashlib.sha256(b"cleartrace-email-v1:" + _auth_key()).digest())
    return Fernet(key).decrypt(ciphertext.encode("ascii")).decode("utf-8")


def _allowed(email: str) -> bool:
    configured = os.environ.get("CLEARTRACE_AUTH_ALLOWED_EMAILS", "").strip()
    if not configured:
        return True
    allowed = {item.strip().lower() for item in configured.split(",") if item.strip()}
    return email.lower() in allowed


def _owner_email() -> str:
    return os.environ.get("CLEARTRACE_OWNER_EMAIL", os.environ.get("CLEARTRACE_SMTP_USERNAME", "")).strip().lower()


def smtp_delivery_enabled() -> bool:
    """Whether SMTP is configured and allowed on this Railway plan."""
    if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RAILWAY_PROJECT_ID"):
        # Railway disables SMTP egress on Hobby/Trial. Fail fast and direct the
        # deployment to the HTTPS provider path instead of timing out at login.
        return False
    username = os.environ.get("CLEARTRACE_SMTP_USERNAME", "").strip()
    password = os.environ.get("CLEARTRACE_SMTP_PASSWORD", "").strip()
    sender = os.environ.get("CLEARTRACE_SMTP_FROM", "").strip() or username
    return bool(username and password and sender)


def email_delivery_enabled() -> bool:
    """Check for an HTTPS email API (Railway-compatible) or local SMTP."""
    resend_ready = bool(
        os.environ.get("CLEARTRACE_RESEND_API_KEY", "").strip()
        and os.environ.get("CLEARTRACE_EMAIL_FROM", "").strip()
    )
    return resend_ready or smtp_delivery_enabled()


def _send_email(to: str, subject: str, body: str) -> None:
    """Send through Resend HTTPS when configured, otherwise local SMTP."""
    api_key = os.environ.get("CLEARTRACE_RESEND_API_KEY", "").strip()
    if api_key:
        sender = os.environ.get("CLEARTRACE_EMAIL_FROM", "").strip()
        if not sender:
            raise RuntimeError("CLEARTRACE_EMAIL_FROM is required with the email API provider.")
        payload = json.dumps({
            "from": sender,
            "to": [to],
            "subject": subject,
            "text": body,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.resend.com/emails", data=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                if response.status not in (200, 201, 202):
                    raise RuntimeError(f"Email provider returned HTTP {response.status}.")
        except urllib.error.HTTPError as exc:
            # Never expose provider response bodies, which may contain addresses
            # or account metadata, to the browser or logs.
            raise RuntimeError(f"Email provider rejected the message (HTTP {exc.code}).") from None
        return

    if not smtp_delivery_enabled():
        raise RuntimeError("No supported email delivery provider is configured.")
    host = os.environ.get("CLEARTRACE_SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("CLEARTRACE_SMTP_PORT", "587"))
    username = os.environ.get("CLEARTRACE_SMTP_USERNAME", "").strip()
    password = os.environ.get("CLEARTRACE_SMTP_PASSWORD", "").replace(" ", "").strip()
    sender = os.environ.get("CLEARTRACE_SMTP_FROM", "").strip() or username
    message = EmailMessage()
    message["Subject"], message["From"], message["To"] = subject, sender, to
    message.set_content(body)
    with smtplib.SMTP(host, port, timeout=12) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(username, password)
        smtp.send_message(message)


def _default_role(email: str) -> str:
    owner = _owner_email()
    return "owner" if owner and email.lower() == owner else "analyst"


def get_role(session_token: str | None) -> str | None:
    user = get_user(session_token)
    return user.get("role") if user else None


def set_user_role(email: str, role: str) -> bool:
    if role not in {"owner", "admin", "analyst", "viewer", "remove"}:
        raise ValueError("Role must be owner, admin, analyst, viewer, or remove.")
    normalized_email = email.strip().lower()
    if role == "owner" and normalized_email != _owner_email():
        raise ValueError("The deployment owner is fixed by CLEARTRACE_OWNER_EMAIL and cannot be reassigned.")
    db = _connect()
    try:
        owner_key, target_key = _email_key(_owner_email()), _email_key(normalized_email)
        db.execute("BEGIN IMMEDIATE")
        owner = db.execute("SELECT workspace_id FROM users WHERE user_key=?", (owner_key,)).fetchone()
        target = db.execute("SELECT user_key FROM users WHERE user_key=?", (target_key,)).fetchone()
        if not owner or not target:
            db.rollback()
            return False
        if target_key == owner_key:
            if role != "owner":
                raise ValueError("The configured organization owner cannot be changed or removed.")
            db.execute("UPDATE users SET role='owner' WHERE user_key=?", (owner_key,))
            db.commit()
            return True
        organization = db.execute("SELECT organization_id FROM organizations WHERE owner_user_key=?", (owner_key,)).fetchone()
        if role == "remove":
            if organization:
                db.execute("DELETE FROM organization_members WHERE user_key=? AND organization_id=?", (target_key, organization["organization_id"]))
            db.commit()
            return True
        if role == "owner":
            raise ValueError("Only the configured owner can hold the owner role.")
        if not organization:
            organization_id = secrets.token_hex(16)
            db.execute("INSERT INTO organizations(organization_id,workspace_id,owner_user_key,created_at) VALUES(?,?,?,?)",
                (organization_id, owner["workspace_id"], owner_key, int(time.time())))
            organization = {"organization_id": organization_id}
        db.execute("INSERT INTO organization_members(user_key,organization_id,role,joined_at) VALUES(?,?,?,?) "
            "ON CONFLICT(user_key) DO UPDATE SET organization_id=excluded.organization_id,role=excluded.role,joined_at=excluded.joined_at",
            (target_key, organization["organization_id"], role, int(time.time())))
        db.commit()
        return True
    finally:
        db.close()


def _send_security_alert(email: str, fingerprint: str, role: str, event: str = "successful sign-in") -> None:
    recipient = _owner_email()
    if not recipient:
        return
    _send_email(recipient, "ClearTrace account and workspace activity",
        f"ClearTrace activity: {event}.\n\n"
        f"Account: {email}\nRole: {role}\nTime (UTC): {datetime.now(timezone.utc).isoformat()}\n"
        f"Network fingerprint: {fingerprint[:12]}\n\n"
        "If you do not recognize this activity, review access to the account and workspace. "
        "This notice contains no dataset contents or sign-in codes."
    )


def _record_login_alert(email: str, ip: str) -> None:
    user_key = _email_key(email)
    fingerprint = _digest(ip[:128], b"ip:")
    db = _connect()
    try:
        db.execute("DELETE FROM login_events WHERE created_at<?", (int(time.time()) - 180 * 86400,))
        db.execute("INSERT INTO login_events(user_key,ip_hash,created_at) VALUES(?,?,?)", (user_key, fingerprint, int(time.time())))
        row = db.execute("SELECT role FROM users WHERE user_key=?", (user_key,)).fetchone()
        role = row["role"] if row else _default_role(email)
    finally:
        db.close()
    if email_delivery_enabled():
        try:
            _send_security_alert(email, fingerprint, role)
        except Exception:
            logger.exception("Owner sign-in notification delivery failed")


def notify_owner_activity(email: str, ip: str, role: str, event: str) -> None:
    """Send a content-free owner notice for a meaningful account/workspace action.

    Callers must pass a fixed event label, never user supplied text. Delivery is
    best-effort so an SMTP outage cannot interrupt the user's workspace action.
    """
    if not email_delivery_enabled():
        return
    try:
        fingerprint = _digest((ip or "unknown")[:128], b"ip:")
        _send_security_alert(email or "Workspace user", fingerprint, role or "unknown", event)
    except Exception:
        logger.exception("Owner activity notification delivery failed")


def google_authorization_url(origin: str) -> tuple[str, str]:
    client_id = os.environ.get("CLEARTRACE_GOOGLE_CLIENT_ID", "").strip()
    if not client_id or not os.environ.get("CLEARTRACE_GOOGLE_CLIENT_SECRET", "").strip():
        raise RuntimeError("Google sign-in is not configured. Add both Google OAuth credentials in Railway.")
    state = secrets.token_urlsafe(32)
    db = _connect()
    try:
        now = int(time.time())
        db.execute("DELETE FROM oauth_states WHERE expires_at<?", (now,))
        db.execute("INSERT INTO oauth_states(state_hash,expires_at) VALUES(?,?)", (_digest(state, b"oauth-state:"), now + 600))
    finally:
        db.close()
    redirect_uri = origin.rstrip("/") + "/api/auth/google/callback"
    query = urllib.parse.urlencode({"client_id": client_id, "redirect_uri": redirect_uri,
        "response_type": "code", "scope": "openid email profile", "state": state, "prompt": "select_account"})
    return "https://accounts.google.com/o/oauth2/v2/auth?" + query, state


def consume_oauth_state(state: str) -> bool:
    if not state or len(state) > 200:
        return False
    db = _connect()
    try:
        digest = _digest(state, b"oauth-state:")
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT expires_at FROM oauth_states WHERE state_hash=?", (digest,)).fetchone()
        db.execute("DELETE FROM oauth_states WHERE state_hash=?", (digest,))
        db.commit()
        return bool(row and row["expires_at"] > int(time.time()))
    finally:
        db.close()


def exchange_google_code(code: str, redirect_uri: str) -> str:
    import requests
    data = urllib.parse.urlencode({"code": code, "client_id": os.environ["CLEARTRACE_GOOGLE_CLIENT_ID"],
        "client_secret": os.environ["CLEARTRACE_GOOGLE_CLIENT_SECRET"], "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"}).encode()
    response = requests.post("https://oauth2.googleapis.com/token", data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=12)
    response.raise_for_status()
    return response.json()["id_token"]


def verify_google_id_token(token: str) -> str:
    """Verify Google's RS256 signature and OIDC claims before using its email."""
    import base64
    import requests
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    def dec(part: str) -> bytes:
        return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))
    parts = token.split(".")
    if len(parts) != 3 or len(token) > 12000:
        raise ValueError("Invalid identity response.")
    header, claims = json.loads(dec(parts[0])), json.loads(dec(parts[1]))
    if header.get("alg") != "RS256" or not header.get("kid"):
        raise ValueError("Unsupported identity signature.")
    response = requests.get("https://www.googleapis.com/oauth2/v3/certs", headers={"Accept": "application/json"}, timeout=10)
    response.raise_for_status()
    keys = response.json().get("keys", [])
    jwk = next((k for k in keys if k.get("kid") == header["kid"] and k.get("kty") == "RSA"), None)
    if not jwk:
        raise ValueError("Identity signing key is unavailable.")
    key = rsa.RSAPublicNumbers(int.from_bytes(dec(jwk["e"]), "big"), int.from_bytes(dec(jwk["n"]), "big")).public_key()
    key.verify(dec(parts[2]), (parts[0] + "." + parts[1]).encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    now = int(time.time())
    if claims.get("iss") not in {"accounts.google.com", "https://accounts.google.com"}:
        raise ValueError("Untrusted identity issuer.")
    if claims.get("exp", 0) <= now or claims.get("iat", now + 1) > now + 60:
        raise ValueError("Identity response expired.")
    if claims.get("aud") != os.environ.get("CLEARTRACE_GOOGLE_CLIENT_ID"):
        raise ValueError("Identity response was issued for another application.")
    if claims.get("email_verified") is not True or not claims.get("email"):
        raise ValueError("A verified Google email is required.")
    return str(claims["email"]).strip().lower()


def create_google_session(email: str) -> tuple[str, str]:
    email = email.strip().lower()
    if not _allowed(email):
        raise ValueError("This account is not enabled for ClearTrace.")
    now, user_key = int(time.time()), _email_key(email)
    db = _connect()
    try:
        user = db.execute("SELECT workspace_id FROM users WHERE user_key=?", (user_key,)).fetchone()
        workspace_id = user["workspace_id"] if user else secrets.token_hex(24)
        if not user:
            db.execute("INSERT INTO users(user_key,email_ciphertext,workspace_id,created_at,role) VALUES(?,?,?,?,?)",
                (user_key, _encrypt_email(email), workspace_id, now, _default_role(email)))
        token = secrets.token_urlsafe(32)
        db.execute("INSERT INTO auth_sessions(token_hash,user_key,expires_at,created_at) VALUES(?,?,?,?)",
            (_digest(token, b"session:"), user_key, now + SESSION_TTL_SECONDS, now))
        db.commit()
        return token, workspace_id
    finally:
        db.close()


def _send_otp(email: str, code: str) -> None:
    _send_email(email, "Your ClearTrace sign-in code",
        f"Your ClearTrace sign-in code is {code}.\n\n"
        "It expires in 10 minutes and can be used once. If you did not request this code, "
        "you can ignore this message. ClearTrace support will never ask you to share it."
    )


def request_code(email: str, ip: str) -> None:
    email = email.strip().lower()
    user_key = _email_key(email)
    now = int(time.time())
    ip_hash = _digest(ip[:128], b"ip:")
    db = _connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM otp_requests WHERE created_at < ?", (now - 3600,))
        previous = db.execute("SELECT sent_at FROM otp_challenges WHERE user_key=?", (user_key,)).fetchone()
        email_count = db.execute(
            "SELECT COUNT(*) FROM otp_requests WHERE user_key=? AND created_at>?",
            (user_key, now - 3600),
        ).fetchone()[0]
        ip_count = db.execute(
            "SELECT COUNT(*) FROM otp_requests WHERE ip_hash=? AND created_at>?",
            (ip_hash, now - 3600),
        ).fetchone()[0]
        if (previous and now - previous["sent_at"] < OTP_COOLDOWN_SECONDS) or email_count >= 5 or ip_count >= 20:
            db.rollback()
            raise ValueError("Please wait before requesting another code.")
        request_row = db.execute("INSERT INTO otp_requests(user_key,ip_hash,created_at) VALUES(?,?,?)", (user_key, ip_hash, now))
        if not _allowed(email):
            db.commit()
            return
        code = f"{secrets.randbelow(1_000_000):06d}"
        code_hash = _digest(email + ":" + code, b"otp:")
        db.execute(
            "INSERT INTO otp_challenges(user_key,code_hash,expires_at,sent_at,attempts) VALUES(?,?,?,?,0) "
            "ON CONFLICT(user_key) DO UPDATE SET code_hash=excluded.code_hash, expires_at=excluded.expires_at, "
            "sent_at=excluded.sent_at, attempts=0",
            (user_key, code_hash, now + OTP_TTL_SECONDS, now),
        )
        db.commit()
        try:
            _send_otp(email, code)
        except Exception:
            db.execute("DELETE FROM otp_challenges WHERE user_key=? AND sent_at=?", (user_key, now))
            db.execute("DELETE FROM otp_requests WHERE rowid=?", (request_row.lastrowid,))
            db.commit()
            logger.exception("OTP email delivery failed")
            raise RuntimeError("We could not send the sign-in email. Check the mail settings and try again.")
    finally:
        db.close()


def verify_code(email: str, code: str, ip: str = "unknown") -> tuple[str, str]:
    """Consume a valid code once; return an opaque auth session and stable workspace id."""
    email = email.strip().lower()
    user_key = _email_key(email)
    code = code.strip()
    if not code.isdigit() or len(code) != 6 or not _allowed(email):
        raise ValueError("That code is invalid or expired. Request a new one.")
    now = int(time.time())
    db = _connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM otp_challenges WHERE user_key=?", (user_key,)).fetchone()
        if not row or row["expires_at"] <= now or row["attempts"] >= OTP_MAX_ATTEMPTS:
            db.execute("DELETE FROM otp_challenges WHERE user_key=?", (user_key,))
            db.commit()
            raise ValueError("That code is invalid or expired. Request a new one.")
        expected = row["code_hash"]
        actual = _digest(email + ":" + code, b"otp:")
        if not hmac.compare_digest(actual, expected):
            attempts = row["attempts"] + 1
            if attempts >= OTP_MAX_ATTEMPTS:
                db.execute("DELETE FROM otp_challenges WHERE user_key=?", (user_key,))
            else:
                db.execute("UPDATE otp_challenges SET attempts=? WHERE user_key=?", (attempts, user_key))
            db.commit()
            if attempts >= OTP_MAX_ATTEMPTS and email_delivery_enabled():
                try:
                    _send_security_alert(email, _digest(ip[:128], b"ip:"), _default_role(email), "repeated invalid sign-in code attempts")
                except Exception:
                    logger.exception("Owner failed-login notification delivery failed")
            raise ValueError("That code is invalid or expired. Request a new one.")
        db.execute("DELETE FROM otp_challenges WHERE user_key=?", (user_key,))
        user = db.execute("SELECT workspace_id FROM users WHERE user_key=?", (user_key,)).fetchone()
        if user:
            workspace_id = user["workspace_id"]
        else:
            workspace_id = secrets.token_hex(24)
            db.execute(
                "INSERT INTO users(user_key,email_ciphertext,workspace_id,created_at,role) VALUES(?,?,?,?,?)",
                (user_key, _encrypt_email(email), workspace_id, now, _default_role(email)),
            )
        session_token = secrets.token_urlsafe(32)
        db.execute("DELETE FROM auth_sessions WHERE expires_at<?", (now,))
        db.execute(
            "INSERT INTO auth_sessions(token_hash,user_key,expires_at,created_at) VALUES(?,?,?,?)",
            (_digest(session_token, b"session:"), user_key, now + SESSION_TTL_SECONDS, now),
        )
        db.commit()
        _record_login_alert(email, ip)
        return session_token, workspace_id
    finally:
        db.close()


def get_user(session_token: str | None) -> dict[str, str] | None:
    if not session_token or len(session_token) > 128:
        return None
    db = _connect()
    try:
        now = int(time.time())
        row = db.execute(
            "SELECT u.email_ciphertext,COALESCE(o.workspace_id,u.workspace_id) AS effective_workspace,"
            "COALESCE(m.role,u.role) AS effective_role FROM auth_sessions s JOIN users u ON u.user_key=s.user_key "
            "LEFT JOIN organization_members m ON m.user_key=u.user_key "
            "LEFT JOIN organizations o ON o.organization_id=m.organization_id "
            "WHERE s.token_hash=? AND s.expires_at>?",
            (_digest(session_token, b"session:"), now),
        ).fetchone()
        if not row:
            return None
        email = _decrypt_email(row["email_ciphertext"])
        role = "owner" if _owner_email() and email == _owner_email() else row["effective_role"]
        return {"email": email, "workspace_id": row["effective_workspace"], "role": role}
    finally:
        db.close()


def logout(session_token: str | None) -> None:
    if not session_token:
        return
    db = _connect()
    try:
        db.execute("DELETE FROM auth_sessions WHERE token_hash=?", (_digest(session_token, b"session:"),))
    finally:
        db.close()


def create_public_demo(ip: str = "unknown") -> tuple[str, str]:
    """Create an expiring, isolated workspace for judges using synthetic data only."""
    token = secrets.token_urlsafe(32)
    workspace_id = secrets.token_hex(24)
    now = int(time.time())
    ip_hash = _digest(ip[:128], b"ip:")
    db = _connect()
    try:
        db.execute("DELETE FROM otp_requests WHERE created_at<?", (now - 3600,))
        recent = db.execute(
            "SELECT COUNT(*) FROM otp_requests WHERE user_key='__public_demo__' AND ip_hash=? AND created_at>?",
            (ip_hash, now - 3600),
        ).fetchone()[0]
        if recent >= 15:
            raise ValueError("Too many sample workspaces were opened from this connection. Try again later.")
        db.execute(
            "INSERT INTO otp_requests(user_key,ip_hash,created_at) VALUES('__public_demo__',?,?)",
            (ip_hash, now),
        )
        expired = db.execute(
            "SELECT workspace_id FROM public_demo_sessions WHERE expires_at<?", (now,)
        ).fetchall()
        db.execute("DELETE FROM public_demo_sessions WHERE expires_at<?", (now,))
        db.execute(
            "INSERT INTO public_demo_sessions(token_hash,workspace_id,expires_at) VALUES(?,?,?)",
            (_digest(token, b"public-demo:"), workspace_id, now + PUBLIC_DEMO_TTL_SECONDS),
        )
        db.commit()
        for row in expired:
            try:
                delete_encrypted_session(row["workspace_id"])
            except Exception:
                logger.debug("Expired judge workspace cleanup deferred")
        return token, workspace_id
    finally:
        db.close()


def get_public_demo(token: str | None) -> dict[str, str] | None:
    if not token or len(token) > 128:
        return None
    db = _connect()
    try:
        row = db.execute(
            "SELECT workspace_id FROM public_demo_sessions WHERE token_hash=? AND expires_at>?",
            (_digest(token, b"public-demo:"), int(time.time())),
        ).fetchone()
        return dict(row) if row else None
    finally:
        db.close()
