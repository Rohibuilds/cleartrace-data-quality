# ClearTrace Security Review Notes

**Review type:** Internal engineering review and automated static scan. This document is not an independent security audit, penetration test, certification, or legal/compliance opinion.

**Reviewed code areas:** `server.py`, `cleartrace/auth.py`, `cleartrace/persistence.py`, ingestion, repair, export, and the browser PWA.

## Implemented controls

- Email OTP challenges are short-lived and single-use, use keyed digests, have bounded attempts and request throttles, and do not place the code in the browser session cookie.
- Auth cookies are HttpOnly and SameSite=Lax, Secure over HTTPS, and mapped to revocable server-side session records.
- User email addresses are encrypted in the auth database; lookup identifiers and session tokens are stored as keyed digests.
- Persisted workspace snapshots use AES-256-GCM authenticated encryption, with session identity bound as additional authenticated data. Key persistence and recovery must be configured by the operator.
- The API adds security headers, origin/CSRF checks for mutations, request limits, and input-format/resource bounds.
- CSV export escapes spreadsheet formula-like values. XLSX macro archives are rejected; PDF and spreadsheet parsing have bounded inputs.
- Repair proposals are separate from mutations; explicit approval is required. Revision guards, audit events, and undo/history code are present.
- Optional Google OIDC validates the provider token and the flow's state. It remains disabled until client settings are supplied.

## Current deployment boundary

The latest recorded Railway check found the public synthetic sample available while SMTP delivery, owner email alerts, and Google sign-in were off. `CLEARTRACE_SMTP_PASSWORD` was absent at that check. Provider-dependent code tests mock SMTP/OAuth and do not prove live message delivery or Google sign-in.

Use only synthetic or non-sensitive data in the public demo. The no-login judge workspace is temporary, isolated, and blocks file uploads. Do not treat the service as a multi-tenant commercial data processor.

## Gaps before a customer production rollout

- Configure and verify the mail provider; add delivery monitoring and tested owner alert handling.
- Use managed identity/SSO and explicit per-tenant authorization policies.
- Move session, membership, and audit state to bounded managed storage with tested expiration and deletion behavior.
- Document key generation, rotation, backup, recovery, and separation of duties.
- Add operational backup/restore drills, retention policies, incident response, monitoring, and abuse controls.
- Commission an independent threat assessment and penetration test against the exact deployed build.
- Review all privacy, regulatory, and contractual requirements for the intended datasets and jurisdictions.

## Verification evidence

See `TEST_REPORT.md` for automated tests, static scan output, deployment checks, and known limitations. A clean static scan and passing test suite are useful evidence, not proof that the application is vulnerability-free.
