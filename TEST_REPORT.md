# ClearTrace — Verification Report

**Verification date:** 20 November 2026 (Asia/Kolkata)

**Source revision tested:** `12c82c0`

**Runtime:** Python 3.9.6, Pytest 8.4.2, Node 26.13.1

**Automated result:** 79 passed, 0 failed, 0 skipped (1.69 seconds)
**Static security scan:** Bandit found 0 enabled issues in `server.py` and `cleartrace/auth.py`.

## Test suite breakdown

| Test file | Tests | Result |
| --- | ---: | --- |
| `tests/test_adversarial.py` | 9 | Pass |
| `tests/test_api.py` | 13 | Pass |
| `tests/test_cleartrace.py` | 8 | Pass |
| `tests/test_cloud_deployment.py` | 12 | Pass |
| `tests/test_cloudflare_tunnel_proxy.py` | 8 | Pass |
| `tests/test_math_intelligence_advanced.py` | 8 | Pass |
| `tests/test_mentor_round.py` | 12 | Pass |
| `tests/test_persistence.py` | 9 | Pass |
| **Total** | **79** | **79 passed** |

The shared `tests/conftest.py` selects explicit local open mode for tests that exercise unrelated API behavior. `tests/test_cloud_deployment.py` separately switches auth on for email OTP and judge-workspace checks. The configured production default remains authentication required.

## Coverage exercised

- Data ingestion, deterministic quality checks, math validation, repair proposals, approvals, undo/reset, exports, and revision handling.
- Session persistence encryption, rehydration, tamper detection, session separation, upload bounds, and injection handling.
- CSRF and reverse-proxy handling, cache policy, API response behavior, and session-isolation guards.
- Email-code flow with SMTP mocked in tests, plus unauthorized API blocking and isolated synthetic judge preview behavior.
- Google OIDC state/callback flow with provider exchange mocked; owner role assignment, viewer write restrictions, and owner-alert triggers are tested with mail mocked.
- Service worker cache version and PWA manifest headers.

## Production verification

Verified on `https://cleartrace-web-production.up.railway.app/` after Railway deployment `f4c7e0d8-1fc6-4b2c-b331-83784ac39032` reported `SUCCESS` (ClearTrace v2.3.1):

| Check | Result |
| --- | --- |
| `GET /health` | 200; healthy, storage ready, v2.3.1 |
| `GET /api/auth/status` without a session | 200; auth required, unauthenticated |
| Protected quality API without a session | 401 |
| `POST /api/auth/public-demo` | 200; sample workspace issued |
| `GET /api/auth/status` integration flags | SMTP delivery off; owner alerts off; Google OIDC off (provider variables absent) |
| Judge workspace auth status | 200; public demo session active |
| `GET /api/quality/score` in judge workspace | 200; score 93.8, grade A |
| File upload from judge workspace | 403; blocked as intended |

The deployed UI was opened and the no-sign-in judge option was exercised in a browser. The sample workspace loaded its synthetic dataset and quality dashboard.

## Security scan and limitations

Bandit reported no enabled issues. One `B104` check is explicitly suppressed at the server's `0.0.0.0` bind, required for the container to accept Railway traffic. The report does not claim an independent security audit or formal compliance certification.

The deployed Railway service reports `smtp_delivery_enabled=false`, `owner_alerts_enabled=false`, and `google_sign_in_enabled=false`. The app code adds email OTP, owner sign-in and repeated-failure alerts, owner-managed account roles, and optional Google OIDC. No Gmail app password or Google OAuth client credentials were supplied; therefore live provider checks cannot be performed. The previous `CLEARTRACE_ACCESS_TOKEN` setting remains absent. Therefore:

- The no-sign-in judge preview is available and verified.
- Personal email-code delivery and owner alerts are **not usable yet** until `CLEARTRACE_SMTP_PASSWORD` and `CLEARTRACE_OWNER_EMAIL` are configured in Railway and a live email is confirmed.
- SMTP and Google token exchange were mocked for unit tests; no real email or Google OAuth sign-in was performed.
- Google OIDC requires `CLEARTRACE_GOOGLE_CLIENT_ID`, `CLEARTRACE_GOOGLE_CLIENT_SECRET`, and `CLEARTRACE_PUBLIC_URL` plus the matching Google Console callback URI; its live sign-in is not verified. It is not SAML/SCIM enterprise provisioning.
- Role and workspace membership behavior is covered locally: assigning an account joins the owner's shared workspace, viewer mutations are rejected, and removing access restores the account's personal workspace. The new shared-role workflow is deployed; exercising it live requires a functioning personal email login.

## Reproduce locally

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/bandit -r server.py cleartrace
node --check static/app.js
node --check static/sw.js
```
