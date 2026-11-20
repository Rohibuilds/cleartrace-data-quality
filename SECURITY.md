# Security notes

## Demo deployment

**Current provider status (20 November 2026):** the public synthetic judge workspace is the working no-login path. Railway Hobby/Trial blocks outbound SMTP, so a Gmail app password alone cannot enable deployed email. Use the Resend HTTPS API with a valid API key and verified sender, then verify a real message. Mocked-provider tests are not proof of live delivery.

The current update clears undelivered OTP challenges and request counts after a send failure, allowing a retry after mail service recovers. Configure `CLEARTRACE_RESEND_API_KEY`, `CLEARTRACE_EMAIL_FROM`, and `CLEARTRACE_OWNER_EMAIL` privately in Railway. SMTP is retained for local/eligible deployments only.

ClearTrace uses email one-time codes for personal workspaces. Codes are single-use, expire after 10 minutes, and have bounded retries and issuance rates. Auth sessions are opaque, revocable server-side records in SQLite; the cookie is HttpOnly and SameSite=Lax, and Secure on HTTPS. Email addresses are encrypted in the auth database and keyed by a keyed digest. User workspaces are keyed to a verified email identity and use the existing encrypted session persistence.

The no-sign-in judge preview is isolated, uses synthetic sample data, and expires after eight hours. Judges can explore and apply repairs to that temporary sample workspace; file uploads are blocked. Configure Resend in Railway with `CLEARTRACE_RESEND_API_KEY`, `CLEARTRACE_EMAIL_FROM` (verified sender), and `CLEARTRACE_OWNER_EMAIL`. Keep all secrets in Railway Variables, never in the repository. `CLEARTRACE_AUTH_ALLOWED_EMAILS` can optionally restrict sign-in; leave it unset for judge self-service.

The OTP database and its private auth key must live on the persistent `/data` volume. The generated local key is stored with mode 0600. Use HTTPS and keep the volume attached across deploys. Failed or unconfigured notifications must not be interpreted as an alert being delivered.

The application creates anonymous session identifiers and can encrypt persisted session snapshots using AES-GCM when the required key is configured. Encryption at rest does not replace authorization, HTTPS, data minimization, backups, retention controls, or key management. Keep secrets in the hosting provider's secret manager, terminate traffic over HTTPS, and avoid uploading sensitive data to a public demo.

The owner receives an email for each successful sign-in and after an account reaches the five-attempt invalid-code limit. Alerts contain the account email, UTC timestamp, role, and a truncated keyed network fingerprint; provider failures are recorded in service logs and never claimed as delivered. Google sign-in is optional: configure `CLEARTRACE_GOOGLE_CLIENT_ID`, `CLEARTRACE_GOOGLE_CLIENT_SECRET`, and `CLEARTRACE_PUBLIC_URL`; register `<CLEARTRACE_PUBLIC_URL>/api/auth/google/callback` as an authorized redirect URI in Google Cloud. The flow checks single-use state, the Google signature, issuer, audience, expiry, and verified email. The Google callback is social/workspace OIDC, not a complete enterprise identity-management suite.

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
