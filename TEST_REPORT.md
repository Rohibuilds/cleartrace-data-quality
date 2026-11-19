# ClearTrace — Verification Report

**Verification date:** 20 November 2026 (Asia/Kolkata)

**Source revision tested:** `b8b9b55` plus the local test-harness corrections listed below

**Runtime:** Python 3.9.6, Pytest 8.4.2, Node 26.13.1

**Automated result:** 76 passed, 0 failed, 0 skipped (1.38 seconds)
**Static security scan:** Bandit found 0 reported issues in 4,727 lines across `server.py` and `cleartrace/`.

## Test suite breakdown

| Test file | Tests | Result |
| --- | ---: | --- |
| `tests/test_adversarial.py` | 9 | Pass |
| `tests/test_api.py` | 13 | Pass |
| `tests/test_cleartrace.py` | 8 | Pass |
| `tests/test_cloud_deployment.py` | 9 | Pass |
| `tests/test_cloudflare_tunnel_proxy.py` | 8 | Pass |
| `tests/test_math_intelligence_advanced.py` | 8 | Pass |
| `tests/test_mentor_round.py` | 12 | Pass |
| `tests/test_persistence.py` | 9 | Pass |
| **Total** | **76** | **76 passed** |

The shared `tests/conftest.py` selects explicit local open mode for tests that exercise unrelated API behavior. `tests/test_cloud_deployment.py` separately switches auth on for email OTP and judge-workspace checks. The configured production default remains authentication required.

## Coverage exercised

- Data ingestion, deterministic quality checks, math validation, repair proposals, approvals, undo/reset, exports, and revision handling.
- Session persistence encryption, rehydration, tamper detection, session separation, upload bounds, and injection handling.
- CSRF and reverse-proxy handling, cache policy, API response behavior, and session-isolation guards.
- Email-code flow with SMTP mocked in tests, plus unauthorized API blocking and isolated synthetic judge preview behavior.
- Service worker cache version and PWA manifest headers.

## Production verification

Verified on `https://cleartrace-web-production.up.railway.app/` after Railway deployment `e40e9e9a-661e-4f51-a031-459fc2f5c5f8` reported `SUCCESS`:

| Check | Result |
| --- | --- |
| `GET /health` | 200; healthy, storage ready |
| `GET /api/auth/status` without a session | 200; auth required, unauthenticated |
| Protected quality API without a session | 401 |
| `POST /api/auth/public-demo` | 200; sample workspace issued |
| Judge workspace auth status | 200; public demo session active |
| `GET /api/quality/score` in judge workspace | 200; score 93.8, grade A |
| File upload from judge workspace | 403; blocked as intended |

The deployed UI was opened and the no-sign-in judge option was exercised in a browser. The sample workspace loaded its synthetic dataset and quality dashboard.

## Security scan and limitations

Bandit reported no enabled issues. One `B104` check is explicitly suppressed at the server's `0.0.0.0` bind, required for the container to accept Railway traffic. The report does not claim an independent security audit or formal compliance certification.

At verification time the Railway configuration included the Gmail sender and SMTP host/port, but **did not include `CLEARTRACE_SMTP_PASSWORD`**. The shared `CLEARTRACE_ACCESS_TOKEN` setting was absent. Therefore:

- The no-sign-in judge preview is available and verified.
- Personal email-code delivery is **not verified** and will not work until the Gmail app password is entered in Railway Variables and the new variable revision is deployed.
- SMTP was mocked for unit tests; no real email was sent during the test run.
- Account login-alert notifications, organization roles, and enterprise identity federation are not covered by this release.

## Reproduce locally

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
.venv/bin/bandit -r server.py cleartrace
node --check static/app.js
node --check static/sw.js
```
