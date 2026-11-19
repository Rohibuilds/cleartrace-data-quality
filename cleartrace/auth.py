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


def _send_otp(email: str, code: str) -> None:
    host = os.environ.get("CLEARTRACE_SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("CLEARTRACE_SMTP_PORT", "587"))
    username = os.environ.get("CLEARTRACE_SMTP_USERNAME", "").strip()
    password = os.environ.get("CLEARTRACE_SMTP_PASSWORD", "").replace(" ", "").strip()
    sender = os.environ.get("CLEARTRACE_SMTP_FROM", "").strip() or username
    if not (username and password and sender):
        raise RuntimeError("Email sign-in is not configured. Set the Gmail SMTP variables in Railway.")
    message = EmailMessage()
    message["Subject"] = "Your ClearTrace sign-in code"
    message["From"] = sender
    message["To"] = email
    message.set_content(
        f"Your ClearTrace sign-in code is {code}.\n\n"
        "It expires in 10 minutes and can be used once. If you did not request this code, "
        "you can ignore this message. ClearTrace support will never ask you to share it."
    )
    context = ssl.create_default_context()
    with smtplib.SMTP(host, port, timeout=15) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(username, password)
        smtp.send_message(message)


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
        db.execute("INSERT INTO otp_requests(user_key,ip_hash,created_at) VALUES(?,?,?)", (user_key, ip_hash, now))
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
            logger.exception("OTP email delivery failed")
            raise RuntimeError("We could not send the sign-in email. Check the mail settings and try again.")
    finally:
        db.close()


def verify_code(email: str, code: str) -> tuple[str, str]:
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
            raise ValueError("That code is invalid or expired. Request a new one.")
        db.execute("DELETE FROM otp_challenges WHERE user_key=?", (user_key,))
        user = db.execute("SELECT workspace_id FROM users WHERE user_key=?", (user_key,)).fetchone()
        if user:
            workspace_id = user["workspace_id"]
        else:
            workspace_id = secrets.token_hex(24)
            db.execute(
                "INSERT INTO users(user_key,email_ciphertext,workspace_id,created_at) VALUES(?,?,?,?)",
                (user_key, _encrypt_email(email), workspace_id, now),
            )
        session_token = secrets.token_urlsafe(32)
        db.execute("DELETE FROM auth_sessions WHERE expires_at<?", (now,))
        db.execute(
            "INSERT INTO auth_sessions(token_hash,user_key,expires_at,created_at) VALUES(?,?,?,?)",
            (_digest(session_token, b"session:"), user_key, now + SESSION_TTL_SECONDS, now),
        )
        db.commit()
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
            "SELECT u.email_ciphertext,u.workspace_id FROM auth_sessions s JOIN users u ON u.user_key=s.user_key "
            "WHERE s.token_hash=? AND s.expires_at>?",
            (_digest(session_token, b"session:"), now),
        ).fetchone()
        return {"email": _decrypt_email(row["email_ciphertext"]), "workspace_id": row["workspace_id"]} if row else None
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
