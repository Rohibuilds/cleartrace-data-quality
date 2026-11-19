"""ClearTrace — Cloud Deployment & Production Hardening Test Suite.

Verifies:
1. Lightweight container healthcheck probe (/health).
2. Rate limiting protection on /api/ endpoints.
3. Access token authorization and demo mode toggle.
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
    """Verify default demo mode allows exploration without requiring token."""
    res = client.get("/api/auth/status")
    assert res.status_code == 200
    data = res.json()
    assert data["demo_mode"] is True
    assert data["auth_required"] is False
    assert data["is_authenticated"] is True


def test_auth_with_access_token(monkeypatch):
    """Verify access control when CLEARTRACE_ACCESS_TOKEN is configured."""
    monkeypatch.setenv("CLEARTRACE_ACCESS_TOKEN", "super-secret-judge-key-999")
    monkeypatch.setenv("CLEARTRACE_DEMO_MODE", "false")

    # Unauthenticated status
    res = client.get("/api/auth/status")
    assert res.status_code == 200
    assert res.json()["is_authenticated"] is False
    assert res.json()["auth_required"] is True

    # Login with invalid token
    login_fail = client.post("/api/auth/login", json={"token": "wrong-password"})
    assert login_fail.status_code == 401

    # Login with valid token
    login_ok = client.post("/api/auth/login", json={"token": "super-secret-judge-key-999"})
    assert login_ok.status_code == 200
    assert login_ok.json()["success"] is True

    # Authenticated via Bearer header
    auth_headers = {"Authorization": "Bearer super-secret-judge-key-999"}
    res_auth = client.get("/api/auth/status", headers=auth_headers)
    assert res_auth.status_code == 200
    assert res_auth.json()["is_authenticated"] is True


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


def test_query_param_token_rejection(monkeypatch):
    """Verify query parameter tokens are rejected (OWASP ASVS / CWE-598)."""
    monkeypatch.setenv("CLEARTRACE_ACCESS_TOKEN", "super-secret-judge-key-999")
    monkeypatch.setenv("CLEARTRACE_DEMO_MODE", "false")

    # Attempt to supply token via URL query string (?token=...)
    res = client.get("/api/auth/status?token=super-secret-judge-key-999")
    assert res.status_code == 200
    # Must NOT authenticate via query param!
    assert res.json()["is_authenticated"] is False


def test_enterprise_mode_blocks_unauthorized_api_endpoints(monkeypatch):
    """Verify CLEARTRACE_DEMO_MODE=false locks down all API routes except health and login."""
    monkeypatch.setenv("CLEARTRACE_ACCESS_TOKEN", "strong-enterprise-secret-token-12345")
    monkeypatch.setenv("CLEARTRACE_DEMO_MODE", "false")

    # Unauthenticated API calls must be blocked with 401
    res_score = client.get("/api/quality/score")
    assert res_score.status_code == 401
    assert "authentication required" in res_score.json()["detail"].lower()

    res_findings = client.get("/api/quality/findings")
    assert res_findings.status_code == 401

    # Health probe remains accessible for container orchestrator
    res_health = client.get("/health")
    assert res_health.status_code == 200

    # Authorized call succeeds
    headers = {"Authorization": "Bearer strong-enterprise-secret-token-12345"}
    res_auth = client.get("/api/quality/score", headers=headers)
    assert res_auth.status_code == 200


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
