# ClearTrace Verification Report

**Verification date:** 20 November 2026 (Asia/Kolkata)
**Source revision tested:** `2632d3d`
**Deployed release:** `v2.3.2`, Railway deployment `53f85fd7-c0ac-4a5b-88e1-3a49e06093c4` (`SUCCESS`)
**Runtime:** Python 3.9.6, Pytest 8.4.2, Node 26.13.1

## Automated checks

**Result:** 80 passed, 0 failed, 0 skipped (1.47 seconds).
**JavaScript:** `node --check static/app.js` and `node --check static/sw.js` passed.
**Static scan:** Bandit reported no enabled findings in `server.py` and `cleartrace/auth.py`; it emitted the expected suppression warning for B104 on the container's `0.0.0.0` bind.

| Test file | Tests | Result |
| --- | ---: | --- |
| `tests/test_adversarial.py` | 9 | Pass |
| `tests/test_api.py` | 13 | Pass |
| `tests/test_cleartrace.py` | 8 | Pass |
| `tests/test_cloud_deployment.py` | 13 | Pass |
| `tests/test_cloudflare_tunnel_proxy.py` | 8 | Pass |
| `tests/test_math_intelligence_advanced.py` | 8 | Pass |
| `tests/test_mentor_round.py` | 12 | Pass |
| `tests/test_persistence.py` | 9 | Pass |
| **Total** | **80** | **80 passed** |

Tests cover data ingestion, deterministic quality checks, math validation, review/apply/undo, exports, revision guards, encryption/tamper detection, API protections, OTP behavior with SMTP mocked, the new unconfigured-mail response, OIDC behavior with provider exchange mocked, role enforcement, and PWA cache headers. Mocked provider tests do not prove real email or Google sign-in.

## Live Railway verification

Service: [https://cleartrace-web-production.up.railway.app/](https://cleartrace-web-production.up.railway.app/)
Deployment: `53f85fd7-c0ac-4a5b-88e1-3a49e06093c4` reported `SUCCESS`.

| Check | Result |
| --- | --- |
| `GET /health` | 200; healthy, storage ready, version 2.3.2 |
| `GET /api/auth/status` | 200; auth required; not signed in; SMTP, owner alerts, Google sign-in all off |
| `POST /api/auth/request-code` with synthetic test address | 503 with the new actionable setup message; no real email attempted |
| `POST /api/auth/public-demo` | 200; temporary sample workspace issued |
| Judge workspace `/api/auth/status` | 200; public sample session active |
| Judge workspace `GET /api/quality/score` | 200; 93.8/100, Grade A |
| `GET /static/app.js` | 200; updated unavailable-mail message present |
| `GET /sw.js` | 200; `cleartrace-shell-v2.3.2` present for PWA cache refresh |

The first public-demo probe used an incorrect cookie-jar setup and returned 401 for the score request. It was repeated with one persistent cookie jar; the demo status and score then returned 200 as expected.

## OTP incident and current status

A phone screenshot showed the sign-in form submitting an email address and returning “We could not send the sign-in email.” The prior Railway status check showed `CLEARTRACE_SMTP_PASSWORD` absent, so the service had no Gmail SMTP password and could not send OTP mail. This was not a problem with the submitted email address.

In revision `2632d3d`, the auth status and request endpoint use one SMTP-configuration check. When mail is unavailable, the API returns a clear 503 response before issuing a challenge; the login UI displays the unavailable state, disables the unusable email action, and points to the public synthetic sample. The fix is deployed and the live API/UI assets were verified. It improves the failure path; it does not enable email delivery.

## Limitations and pending provider verification

- **Personal email OTP and owner email alerts are still unavailable** until `CLEARTRACE_SMTP_PASSWORD` is entered in Railway Variables and a real message is tested. Do not share the app password in chat or source control.
- Google OIDC is off until Google OAuth client credentials and the matching callback are configured and live-tested.
- Organization role behavior has automated coverage, but live member sign-in requires working email OTP.
- This is not an independent security audit, a compliance certification, or a production multi-tenant SaaS approval. See `SECURITY.md` and `RELEASE_READINESS.md`.
