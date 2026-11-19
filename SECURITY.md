# Security notes

## Demo deployment

ClearTrace currently uses one configured `CLEARTRACE_ACCESS_TOKEN` for access control. Anyone who knows that token shares the same demo access boundary; this is not individual user authentication, role-based authorization, or account takeover detection. Do not publish the token, place it in a URL, commit it, or embed it in client-side code. Rotate it if it may have been exposed.

The application creates anonymous session identifiers and can encrypt persisted session snapshots using AES-GCM when the required key is configured. Encryption at rest does not replace authorization, HTTPS, data minimization, backups, retention controls, or key management. Keep secrets in the hosting provider's secret manager, terminate traffic over HTTPS, and avoid uploading sensitive data to a public demo.

Email and SMS alert delivery only works when the corresponding provider credentials and sender configuration are valid. Failed or unconfigured notifications must not be interpreted as a security alarm being delivered.

## Production requirements

Before inviting general users or processing confidential datasets, add and independently review:

- Individual identity (OIDC/OAuth) with tenant and dataset-level authorization.
- Rate limits and abuse controls for login, uploads, scans, and repairs.
- Bounded, shared session storage with expiration and deletion policies.
- Security event logging and delivery monitoring, without logging credentials or dataset contents.
- A documented encryption-key lifecycle, backups, retention, recovery, and incident response.
- A deployment-specific threat model and independent security review.

Report security issues privately to the repository owner. Do not put access tokens, passwords, private datasets, or provider credentials in issues or pull requests.
