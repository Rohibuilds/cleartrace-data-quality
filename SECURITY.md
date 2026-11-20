# Security notes

## Demo deployment

**Current provider status (20 November 2026):** the public synthetic judge workspace is the working no-login path. The most recent Railway status check reported email delivery, owner alerts, and Google sign-in disabled. Do not interpret the implementation or mocked-provider tests as proof of live email/OIDC delivery. OTP UI/API now surfaces missing mail setup before a code request; a real sign-in still requires SMTP configuration and a live test.

The 2.3.5 update clears undelivered OTP challenges and request counts after SMTP failure, allowing a retry after mail service recovers. The owner activity recipient is configured privately in Railway. Delivery remains unavailable until `CLEARTRACE_SMTP_PASSWORD` is added privately and a real message is verified.

ClearTrace uses email one-time codes for personal workspaces. Codes are single-use, expire after 10 minutes, and have bounded retries and issuance rates. Auth sessions are opaque, revocable server-side records in SQLite; the cookie is HttpOnly and SameSite=Lax, and Secure on HTTPS. Email addresses are encrypted in the auth database and keyed by a keyed digest. User workspaces are keyed to a verified email identity and use the existing encrypted session persistence.

The no-sign-in judge preview is isolated, uses synthetic sample data, and expires after eight hours. Judges can explore and apply repairs to that temporary sample workspace; file uploads are blocked. Configure Gmail SMTP in Railway with `CLEARTRACE_SMTP_USERNAME`, `CLEARTRACE_SMTP_PASSWORD` (a Google app password), `CLEARTRACE_SMTP_FROM`, and optionally `CLEARTRACE_SMTP_HOST` / `CLEARTRACE_SMTP_PORT`. Set `CLEARTRACE_OWNER_EMAIL` to the address that should receive security alerts and become the initial owner. Keep all secrets in Railway Variables, never in the repository. `CLEARTRACE_AUTH_ALLOWED_EMAILS` can optionally restrict sign-in; leave it unset for judge self-service.

The OTP database and its private auth key must live on the persistent `/data` volume. The generated local key is stored with mode 0600. Use HTTPS and keep the volume attached across deploys. Failed or unconfigured notifications must not be interpreted as an alert being delivered.

The application creates anonymous session identifiers and can encrypt persisted session snapshots using AES-GCM when the required key is configured. Encryption at rest does not replace authorization, HTTPS, data minimization, backups, retention controls, or key management. Keep secrets in the hosting provider's secret manager, terminate traffic over HTTPS, and avoid uploading sensitive data to a public demo.

The owner receives an email for each successful sign-in and after an account reaches the five-attempt invalid-code limit. Alerts contain the account email, UTC timestamp, role, and a truncated keyed network fingerprint; SMTP failures are recorded in service logs and never claimed as delivered. Google sign-in is optional: configure `CLEARTRACE_GOOGLE_CLIENT_ID`, `CLEARTRACE_GOOGLE_CLIENT_SECRET`, and `CLEARTRACE_PUBLIC_URL`; register `<CLEARTRACE_PUBLIC_URL>/api/auth/google/callback` as an authorized redirect URI in Google Cloud. The flow checks single-use state, the Google signature, issuer, audience, expiry, and verified email. The Google callback is social/workspace OIDC, not a complete enterprise identity-management suite.

Roles are `owner`, `admin`, `analyst`, and `viewer`. Only the configured owner can assign or remove access for an account that has already signed in. Assignment joins the account to the owner's shared organization workspace; members can access shared datasets according to their role. Removing access restores the account's own workspace. Viewer accounts cannot upload, apply repairs, reset, restore, or edit math rules. This deployment supports one owner-managed organization; SAML, SCIM, multi-organization tenancy, and managed team provisioning are not included.

## Production requirements

Before inviting general users or processing confidential datasets, add and independently review:

- Multi-organization tenancy, SAML/SCIM, and administrator-managed tenant policies.
- Rate limits and abuse controls for login, uploads, scans, and repairs.
- Bounded, shared session storage with expiration and deletion policies.
- Security event logging and delivery monitoring, without logging credentials or dataset contents.
- A documented encryption-key lifecycle, backups, retention, recovery, and incident response.
- A deployment-specific threat model and independent security review.

Report security issues privately to the repository owner. Do not put passwords, one-time codes, private datasets, or provider credentials in issues or pull requests.
