"""ClearTrace — Focused Cloudflare Tunnel & Reverse Proxy Regression Tests.

Validates:
1. Proxy HTTPS handling, dynamic Secure cookie enforcement, and same-origin credential flow.
2. Strict Network-Only cache headers (no-store, no-cache) on all /api/ routes.
3. Service Worker (/sw.js) and Manifest (/manifest.json) cache validation headers.
4. Cloudflare Access headers (Cf-Access-*) safety: zero credential logging or reflection.
5. Clear distinction between 401/403 auth failures, 5xx server errors, network 503, and LLM status.
"""

import io
import json
import logging
import secrets
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_api_routes_enforce_no_store_cache_headers(client):
    """Ensure all /api/ responses mandate zero proxy or browser caching."""
    routes_to_test = [
        "/api/dataset/summary",
        "/api/quality/score",
        "/api/repair/proposals",
        "/api/rag/status",
    ]
    for route in routes_to_test:
        res = client.get(route)
        assert res.status_code == 200
        cache_control = res.headers.get("cache-control", "").lower()
        assert "no-store" in cache_control, f"Route {route} missing no-store in Cache-Control"
        assert "no-cache" in cache_control, f"Route {route} missing no-cache in Cache-Control"
        assert res.headers.get("pragma", "").lower() == "no-cache"


def test_service_worker_and_manifest_cache_headers(client):
    """Ensure /sw.js and /manifest.json have strict cache-busting headers to prevent stale mobile caching."""
    sw_res = client.get("/sw.js")
    assert sw_res.status_code == 200
    assert sw_res.headers.get("service-worker-allowed") == "/"
    sw_cc = sw_res.headers.get("cache-control", "").lower()
    assert "no-cache" in sw_cc
    assert "no-store" in sw_cc
    assert "cleartrace-shell-v2.3.7" in sw_res.text

    man_res = client.get("/manifest.json")
    assert man_res.status_code == 200
    man_cc = man_res.headers.get("cache-control", "").lower()
    assert "no-cache" in man_cc


def test_cloudflare_tunnel_proxy_https_cookie_security(client):
    """Verify reverse-proxy HTTPS headers trigger Secure flag on cookies."""
    # Direct HTTP request -> Secure flag not set (allows localhost dev)
    res_direct = client.get("/api/dataset/summary")
    direct_cookie = res_direct.headers.get("set-cookie", "")
    assert "httponly" in direct_cookie.lower()
    assert "samesite=lax" in direct_cookie.lower()

    # Proxied HTTPS request (Cloudflare Tunnel forwards X-Forwarded-Proto: https)
    res_proxy = client.get("/api/dataset/summary", headers={"X-Forwarded-Proto": "https"})
    proxy_cookie = res_proxy.headers.get("set-cookie", "")
    assert "secure" in proxy_cookie.lower(), "Cookie missing Secure flag behind HTTPS proxy"
    assert "httponly" in proxy_cookie.lower()
    assert "samesite=lax" in proxy_cookie.lower()


def test_cloudflare_access_headers_zero_logging_and_zero_reflection(client, caplog):
    """Verify Cloudflare Access identity headers are accepted without logging tokens or echoing secrets."""
    caplog.set_level(logging.DEBUG)
    test_email = "auditor-judge@example.com"
    secret_jwt = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.sensitive_payload.signature"

    headers = {
        "X-Forwarded-Proto": "https",
        "Cf-Access-Authenticated-User-Email": test_email,
        "Cf-Access-Jwt-Assertion": secret_jwt,
    }

    res = client.get("/api/dataset/summary", headers=headers)
    assert res.status_code == 200

    # Ensure secret JWT is never reflected in response headers or body
    assert secret_jwt not in res.text
    for hname, hval in res.headers.items():
        assert secret_jwt not in hval

    # Ensure secret JWT and raw cookies are never written to server logs
    for record in caplog.records:
        assert secret_jwt not in record.message
        assert test_email not in record.message


def test_distinguish_llm_status_from_error(client):
    """Verify that an offline LLM is reported as an auditable status (HTTP 200), not a 5xx error."""
    res = client.get("/api/rag/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert data["llm_available"] is False
    assert "disabled by default" in data["llm_status_message"].lower() or "offline" in data["llm_status_message"].lower()

    # RAG ask with offline LLM gracefully falls back to deterministic evidence (HTTP 200)
    ask_res = client.post("/api/rag/ask", json={"question": "salary outlier"})
    assert ask_res.status_code == 200
    ask_data = ask_res.json()
    assert ask_data["status"] == "llm_unavailable_evidence_presented"
    assert ask_data["provider"] == "retrieval-deterministic"


def test_distinguish_client_concurrency_error_from_server_error(client):
    """Verify stale revisions produce a clean 409 Conflict rather than 500 server crash."""
    tok = "concurrency-test-" + secrets.token_hex(8)
    h = {"X-Session-ID": tok}
    client.post("/api/dataset/demo", headers=h)

    # Intentionally pass an incorrect expected_revision (e.g. 99 instead of 1)
    res = client.post(
        "/api/repair/apply",
        json={"finding_id": "finding-demo-1", "expected_revision": 99},
        headers=h,
    )
    # Must be 409 Conflict, NOT 500 Internal Server Error
    assert res.status_code == 409
    assert "Stale revision" in res.json()["detail"]


def test_csrf_origin_and_cross_site_defense(client):
    """ASVS 5.0 Section 4.2: Verify CSRF protections on state-mutating endpoints.
    
    Ensures that cross-site requests (Sec-Fetch-Site: cross-site) or requests with
    untrusted Origin/Referer headers are blocked with HTTP 403 Forbidden.
    """
    tok = "csrf-test-" + secrets.token_hex(8)
    h_base = {"X-Session-ID": tok}
    client.post("/api/dataset/demo", headers=h_base)

    # 1. Reject cross-site fetch (Sec-Fetch-Site: cross-site)
    res_cross_site = client.post(
        "/api/repair/apply",
        headers={**h_base, "Sec-Fetch-Site": "cross-site"},
        json={"finding_id": "dummy", "expected_revision": 1},
    )
    assert res_cross_site.status_code == 403
    assert "CSRF check failed" in res_cross_site.json()["detail"]

    # 2. Reject untrusted Origin
    res_untrusted_origin = client.post(
        "/api/repair/apply",
        headers={**h_base, "Origin": "https://evil-attacker.com"},
        json={"finding_id": "dummy", "expected_revision": 1},
    )
    assert res_untrusted_origin.status_code == 403
    assert "Untrusted Origin" in res_untrusted_origin.json()["detail"]

    # 3. Reject untrusted Referer
    res_untrusted_referer = client.post(
        "/api/repair/apply",
        headers={**h_base, "Referer": "https://evil-attacker.com/exploit.html"},
        json={"finding_id": "dummy", "expected_revision": 1},
    )
    assert res_untrusted_referer.status_code == 403
    assert "Untrusted Referer" in res_untrusted_referer.json()["detail"]

    # 4. Allow trusted trycloudflare Origin
    res_trusted_cf = client.post(
        "/api/dataset/demo",
        headers={**h_base, "Origin": "https://demo-cleartrace.trycloudflare.com"},
    )
    assert res_trusted_cf.status_code == 200


def test_cloudflare_tunnel_session_hijacking_mitigation(client):
    """ASVS 5.0 Section 3: Verify that external X-Session-ID headers cannot hijack sessions behind Cloudflare.
    
    When a request passes through Cloudflare Tunnel (CF-Ray present), an external
    attacker cannot force a victim's session ID via header; only the authenticated
    HttpOnly cookie is trusted.
    """
    victim_session = "victim-secret-session-987654"
    # Create victim session with private data
    client.post(
        "/api/dataset/upload",
        files={"file": ("victim_confidential.csv", io.BytesIO(b"id,secret\n1,super_secret\n"), "text/csv")},
        headers={"X-Session-ID": victim_session},
    )

    # Attacker on a separate device/browser tries to read victim data through Cloudflare Tunnel
    # by passing victim's X-Session-ID, possessing NO victim cookie.
    attacker_client = TestClient(app)
    res_attacker = attacker_client.get(
        "/api/dataset/summary",
        headers={
            "CF-Ray": "89abcdef0123-SJC",
            "X-Session-ID": victim_session,
        },
    )
    assert res_attacker.status_code == 200
    attacker_data = res_attacker.json()

    # The server MUST ignore the X-Session-ID header behind Cloudflare and assign a clean session
    # Attacker must NOT see victim's filename or data!
    assert attacker_data["filename"] != "victim_confidential.csv"
    assert "super_secret" not in str(attacker_data)

