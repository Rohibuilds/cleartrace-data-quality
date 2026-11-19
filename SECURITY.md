# Security notes

## Demo deployment

ClearTrace uses email one-time codes for personal workspaces. Codes are single-use, expire after 10 minutes, and have bounded retries and issuance rates. Auth sessions are opaque, revocable server-side records in SQLite; the cookie is HttpOnly and SameSite=Lax, and Secure on HTTPS. Email addresses are encrypted in the auth database and keyed by a keyed digest. User workspaces are keyed to a verified email identity and use the existing encrypted session persistence.

The no-sign-in judge preview is isolated, uses synthetic sample data, and expires after eight hours. Judges can explore and apply repairs to that temporary sample workspace; file uploads are blocked. Configure Gmail SMTP in Railway with `CLEARTRACE_SMTP_USERNAME`, `CLEARTRACE_SMTP_PASSWORD` (a Google app password), and optionally `CLEARTRACE_SMTP_FROM`, `CLEARTRACE_SMTP_HOST`, and `CLEARTRACE_SMTP_PORT`. Keep these in Railway Variables, never in the repository. `CLEARTRACE_AUTH_ALLOWED_EMAILS` can optionally restrict who may receive codes; leave it unset for judge self-service sign-in.

The OTP database and its private auth key must live on the persistent `/data` volume. The generated local key is stored with mode 0600. Use HTTPS and keep the volume attached across deploys. Failed or unconfigured notifications must not be interpreted as an alert being delivered.

The application creates anonymous session identifiers and can encrypt persisted session snapshots using AES-GCM when the required key is configured. Encryption at rest does not replace authorization, HTTPS, data minimization, backups, retention controls, or key management. Keep secrets in the hosting provider's secret manager, terminate traffic over HTTPS, and avoid uploading sensitive data to a public demo.

Other security alert email and SMS delivery only works when the corresponding provider credentials and sender configuration are valid. OTP delivery is separate from account activity alerting.

## Production requirements

Before inviting general users or processing confidential datasets, add and independently review:

- Organization identity (OIDC/OAuth), roles, and administrator-managed tenant policies.
- Rate limits and abuse controls for login, uploads, scans, and repairs.
- Bounded, shared session storage with expiration and deletion policies.
- Security event logging and delivery monitoring, without logging credentials or dataset contents.
- A documented encryption-key lifecycle, backups, retention, recovery, and incident response.
- A deployment-specific threat model and independent security review.

Report security issues privately to the repository owner. Do not put passwords, one-time codes, private datasets, or provider credentials in issues or pull requests.
