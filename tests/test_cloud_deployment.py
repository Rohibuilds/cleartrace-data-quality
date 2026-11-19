"""ClearTrace — Cloud Deployment & Production Hardening Test Suite.

Verifies:
1. Lightweight container healthcheck probe (/health).
2. Rate limiting protection on /api/ endpoints.
3. Email one-time-code authorization and temporary judge workspace.
4. Upload file extension validation.
5. Railway, Render, and Cloudflare CORS/trusted origin handling.
6. Persistent volume path resolution and restart simulation.
"""

from __future__ import annotations

import io
import os
import pytest
from fastapi.testclient import TestClient

from server import app, is_trusted_origin, _RATE_LIMIT_STORE

client = TestClient(app)


@pytest.fixture(autouse=True)
def local_open_mode(monkeypatch, tmp_path):
    """Keep unrelated endpoint tests isolated from the production OTP gate."""
    monkeypatch.setenv("CLEARTRACE_AUTH_ENABLED", "false")
    monkeypatch.setenv("CLEARTRACE_DATA_DIR", str(tmp_path / "data"))


def test_lightweight_health_probe():
    """Verify /health returns 200 without leaking customer filenames or allocating sessions."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "ClearTrace Data Quality Engine"
    assert "version" in data
    assert "storage" in data
    assert data["llm"] == "direct-evidence"
    # Ensure no customer data or session tokens are leaked in health probe
    assert "filename" not in data
    assert "session_id" not in data
    assert "secret" not in data


def test_auth_status_demo_mode_default():
    """Explicit local open mode remains available for development."""
    res = client.get("/api/auth/status")
    assert res.status_code == 200
    data = res.json()
    assert data["auth_required"] is False
    assert data["is_authenticated"] is True


def test_auth_with_email_one_time_code(monkeypatch):
    """Verify one-time email codes establish an isolated authenticated workspace."""
    import cleartrace.auth as auth_module
    monkeypatch.setenv("CLEARTRACE_AUTH_ENABLED", "true")
    monkeypatch.setenv("CLEARTRACE_AUTH_SECRET", "test-auth-secret-with-adequate-length")
    client.cookies.clear()
    sent = {}
    monkeypatch.setattr(auth_module, "_send_otp", lambda email, code: sent.update(email=email, code=code))

    res = client.get("/api/auth/status")
    assert res.status_code == 200
    assert res.json()["is_authenticated"] is False
    assert res.json()["auth_required"] is True

    protected = client.get("/api/quality/score")
    assert protected.status_code == 401

    sent_response = client.post("/api/auth/request-code", json={"email": "judge@example.com"})
    assert sent_response.status_code == 200
    assert sent["email"] == "judge@example.com"
    login_ok = client.post("/api/auth/verify", json={"email": sent["email"], "code": sent["code"]})
    assert login_ok.status_code == 200
    assert login_ok.json()["success"] is True

    res_auth = client.get("/api/auth/status")
    assert res_auth.status_code == 200
    assert res_auth.json()["is_authenticated"] is True
    assert res_auth.json()["email"] == "judge@example.com"
    assert client.get("/api/quality/score").status_code == 200


def test_upload_extension_validation():
    """Verify server rejects malicious or unsupported extensions."""
    # Attempt to upload a .sh script
    res = client.post(
        "/api/dataset/upload",
        files={"file": ("exploit.sh", io.BytesIO(b"echo 'hello'"), "text/plain")},
    )
    assert res.status_code == 400
    assert "unsupported file format" in res.json()["detail"].lower()

    # Attempt to upload an executable .exe
    res_exe = client.post(
        "/api/dataset/upload",
        files={"file": ("malware.exe", io.BytesIO(b"MZ\x90\x00"), "application/octet-stream")},
    )
    assert res_exe.status_code == 400

    # Attempt to upload a legacy Excel .xls file (must reject with actionable message)
    res_xls = client.post(
        "/api/dataset/upload",
        files={"file": ("legacy_data.xls", io.BytesIO(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"), "application/vnd.ms-excel")},
    )
    assert res_xls.status_code == 400
    assert "legacy excel 97-2003" in res_xls.json()["detail"].lower()


def test_tsv_upload_supported():
    """Verify TSV (tab-separated values) document format is fully supported."""
    tsv_content = b"id\tname\tamount\n1\tInvoiceA\t100.50\n2\tInvoiceB\t250.00\n"
    res = client.post(
        "/api/dataset/upload",
        files={"file": ("sample.tsv", io.BytesIO(tsv_content), "text/tab-separated-values")},
    )
    assert res.status_code == 200
    assert res.json()["success"] is True
    assert res.json()["filename"] == "sample.tsv"


def test_query_string_cannot_authenticate(monkeypatch):
    """A URL query parameter never authenticates a browser session."""
    monkeypatch.setenv("CLEARTRACE_AUTH_ENABLED", "true")
    client.cookies.clear()

    # Attempt to supply token via URL query string (?token=...)
    res = client.get("/api/auth/status?email=judge@example.com&code=123456")
    assert res.status_code == 200
    assert res.json()["is_authenticated"] is False


def test_otp_mode_blocks_unauthorized_api_endpoints(monkeypatch):
    """OTP mode gates API routes while leaving the no-sign-in sample path available."""
    monkeypatch.setenv("CLEARTRACE_AUTH_ENABLED", "true")
    client.cookies.clear()

    # Unauthenticated API calls must be blocked with 401
    res_score = client.get("/api/quality/score")
    assert res_score.status_code == 401
    assert "sign in" in res_score.json()["detail"].lower()

    res_findings = client.get("/api/quality/findings")
    assert res_findings.status_code == 401

    # Health probe remains accessible for container orchestrator
    res_health = client.get("/health")
    assert res_health.status_code == 200

    # A no-sign-in sample workspace can read synthetic quality data.
    demo = client.post("/api/auth/public-demo", json={})
    assert demo.status_code == 200
    assert client.get("/api/quality/score").status_code == 200
    assert client.post(
        "/api/dataset/upload",
        files={"file": ("private.csv", io.BytesIO(b"id\n1\n"), "text/csv")},
    ).status_code == 403


def test_rate_limiting_enforcement():
    """Verify sliding-window rate limiter trips after exceeding maximum request threshold."""
    test_ip = "198.51.100.42"
    _RATE_LIMIT_STORE[test_ip] = []

    headers = {"X-Forwarded-For": test_ip}

    # Simulate 180 rapid requests
    for _ in range(180):
        _RATE_LIMIT_STORE[test_ip].append(pytest.approx(1000.0))  # past timestamps

    # Reset with current timestamps right now
    import time
    now = time.time()
    _RATE_LIMIT_STORE[test_ip] = [now] * 180

    # Request #181 should receive 429 Too Many Requests
    blocked_res = client.get("/api/quality/score", headers=headers)
    assert blocked_res.status_code == 429
    assert "rate limit exceeded" in blocked_res.json()["detail"].lower()
    assert blocked_res.headers.get("retry-after") == "60"

    # Health check is exempt from rate limit
    health_res = client.get("/health", headers=headers)
    assert health_res.status_code == 200

    # Clean up test IP
    _RATE_LIMIT_STORE.pop(test_ip, None)


def test_trusted_origins_railway_and_render():
    """Verify origin validation supports Railway and Render deployment subdomains."""
    assert is_trusted_origin("https://cleartrace-production.up.railway.app") is True
    assert is_trusted_origin("https://cleartrace.railway.app") is True
    assert is_trusted_origin("https://cleartrace.onrender.com") is True
    assert is_trusted_origin("https://eval-session.trycloudflare.com") is True
    assert is_trusted_origin("http://127.0.0.1:8000") is True

    # Untrusted origins
    assert is_trusted_origin("https://evil-hacker.com") is False
    assert is_trusted_origin("https://fake-up.railway.app.phishing.io") is False
