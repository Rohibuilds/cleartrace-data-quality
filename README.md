<div align="center">

# ClearTrace

### Every issue explained. Every fix traceable.

**A review-first data quality workspace for Problem 01 — DataFix**

[Open the live demo](https://cleartrace-web-production.up.railway.app/) · [Security notes](SECURITY.md) · [Deployment guide](DEPLOYMENT.md)

</div>

---

ClearTrace helps teams find data quality issues, understand why they matter, and review proposed repairs before applying them. Each accepted change can be revalidated and traced through revisions and audit records.

## Product workflow

**Import → Inspect → Explain → Propose → Review → Revalidate → Export**

The product is designed to keep data repair visible and deliberate: findings are evidence, suggestions are reviewable, and a person decides whether a repair should be applied.

## Features

- **Quality inspection:** missing values, duplicates, whitespace, category variations, invalid dates, invalid numeric values, and statistical outliers.
- **Reviewable repairs:** inspect before/after values; edit, approve, or reject proposed changes before mutation.
- **Revalidation and history:** rescan after changes, compare revisions, use undo/time-machine history, and inspect the audit ledger.
- **Data tools:** mathematical validation, explainability, citation-oriented knowledge assistance, data passports, and executive exports.
- **Multiple data formats:** CSV and spreadsheet workflows, with PDF support in selected import and math workflows.
- **Phone-ready PWA:** responsive interface, touch navigation, install metadata, and a cached app shell for offline launch.
- **Privacy-conscious processing:** browser sessions are isolated; the app does not intentionally send uploaded dataset contents to third-party AI services.

## Try the deployed demo

Open [cleartrace-web-production.up.railway.app](https://cleartrace-web-production.up.railway.app/). Judges can choose **Explore sample workspace** to inspect and repair synthetic data without signing in. On Railway Hobby/Trial, outbound SMTP is blocked, so OTP delivery must use an HTTPS email API. ClearTrace supports Resend through `CLEARTRACE_RESEND_API_KEY` and a verified `CLEARTRACE_EMAIL_FROM` sender. File uploads are limited to verified email workspaces.

Use synthetic or non-sensitive data for the public demo. The current deployment is a controlled demonstration, not a multi-tenant commercial service.

## Run locally

Python 3.10 or later is recommended.

```bash
git clone https://github.com/Rohibuilds/cleartrace-data-quality.git
cd cleartrace-data-quality
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

For Railway and other hosts that restrict SMTP, configure Resend (or use local Gmail SMTP for development). Store credentials only in a secret manager:

```bash
export CLEARTRACE_RESEND_API_KEY="re_..."
export CLEARTRACE_EMAIL_FROM="ClearTrace <verified-sender@your-domain.example>"
export CLEARTRACE_OWNER_EMAIL="owner@example.com"
export CLEARTRACE_AUTH_ENABLED=true
python run.py
```

For local development only, `CLEARTRACE_SMTP_USERNAME`, `CLEARTRACE_SMTP_PASSWORD`, and `CLEARTRACE_SMTP_FROM` can be used when outbound SMTP is available. A Gmail app password does not bypass Railway's SMTP network restriction.

Open `http://127.0.0.1:8000`. To start the companion Streamlit studio instead:

```bash
python run.py --streamlit
```

For hosted deployments, configure these values in the provider's secret manager. Never commit `.env` files, email credentials, or encryption keys.

## Install on a phone

- **iPhone:** open the HTTPS demo in Safari, tap **Share**, then **Add to Home Screen**.
- **Android:** open the HTTPS demo in Chrome and choose **Install app** from the browser menu.

The cached offline shell can launch the interface, but sign-in, uploads, and API operations need an internet connection. Email OTP creates an individual email identity and persistent workspace. Google OpenID Connect sign-in and owner-managed organization roles can be enabled with the deployment settings in [DEPLOYMENT.md](DEPLOYMENT.md). Assigning a role adds that signed-in account to the shared organization workspace; removing access restores the user's private workspace.

## Architecture

| Layer | Location | Responsibility |
| --- | --- | --- |
| PWA interface | `static/` | Responsive single-page app, navigation, install assets, and offline shell |
| HTTP API | `server.py` | Authentication gate, session handling, scan/repair endpoints, exports |
| Quality engine | `cleartrace/` | Ingestion, deterministic checks, repair policies, scoring, audit, and persistence |
| Companion interface | `app.py` and `datafix/` | Streamlit workflows and earlier studio implementation |
| Samples and tests | `samples/`, `tests/` | Synthetic datasets and automated test cases |
| Product specifications | `spec/`, `engineering/` | Functional, security, architecture, and acceptance documentation |
| Submission materials | `submission/` | Submission checklist, PDF brief, and short demo script |

## Security and known limits

If an email send fails, ClearTrace removes that undelivered code and its request count so the account can retry when mail service returns. The owner alert address is configured privately as `CLEARTRACE_OWNER_EMAIL`.

ClearTrace uses short-lived, single-use email codes for sign-in. Owner-managed roles share a deployment organization workspace and limit viewer mutations. The owner at `CLEARTRACE_OWNER_EMAIL` receives content-free notices for sign-ins and workspace activity when an email provider is configured. Notices contain no dataset rows or uploaded contents. Delivery is best-effort; failed mail does not undo workspace changes. Google OIDC is optional and requires a configured OAuth client. This release does not include SAML, SCIM, multi-organization tenancy, or organization policy administration. Encrypted persistence does not replace key management, retention policies, backups, or monitoring.

Before handling confidential or regulated data, a production operator should add managed identity, per-user authorization and isolation, rate limiting, bounded shared session storage, backup and retention policies, and independent security review. Read [SECURITY.md](SECURITY.md) and the deployment checklist before exposing a new instance.

## Development checks

```bash
python -m pytest -q
node --check static/app.js
```

The repository contains test and security reports from project development. Re-run checks against the exact commit and deployment before treating those reports as current verification.

## Submission materials

- [Submission details and remaining handoff items](submission/SUBMISSION_PACK.md)
- [Under-three-minute video script](submission/VIDEO_SCRIPT.md)
- [Downloadable submission brief](submission/ClearTrace_Submission_Brief.pdf)

## License

No license has been selected. Unless a license is added, standard copyright restrictions apply; public visibility does not grant permission to reuse the code.
