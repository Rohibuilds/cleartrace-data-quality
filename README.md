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

Open [cleartrace-web-production.up.railway.app](https://cleartrace-web-production.up.railway.app/). Judges can choose **Explore sample workspace** to inspect and repair synthetic data without signing in. To keep a personal workspace across visits, enter an email address and verify the one-time code delivered to that inbox. File uploads are limited to verified email workspaces.

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

Configure Gmail SMTP for email sign-in, then start the FastAPI/PWA app. Use a Gmail app password stored only in your shell or secret manager:

```bash
export CLEARTRACE_SMTP_USERNAME="your-sender@gmail.com"
export CLEARTRACE_SMTP_PASSWORD="your-16-character-app-password"
export CLEARTRACE_SMTP_FROM="$CLEARTRACE_SMTP_USERNAME"
export CLEARTRACE_AUTH_ENABLED=true
python run.py
```

Open `http://127.0.0.1:8000`. To start the companion Streamlit studio instead:

```bash
python run.py --streamlit
```

For hosted deployments, configure these values in the provider's secret manager. Never commit `.env` files, email credentials, or encryption keys.

## Install on a phone

- **iPhone:** open the HTTPS demo in Safari, tap **Share**, then **Add to Home Screen**.
- **Android:** open the HTTPS demo in Chrome and choose **Install app** from the browser menu.

The cached offline shell can launch the interface, but sign-in, uploads, and API operations need an internet connection. Email OTP creates an individual email identity and persistent workspace; it is not an organization identity provider or role-management system.

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

ClearTrace uses short-lived, single-use email codes for sign-in and keeps account workspaces isolated. The public judge preview can inspect and repair synthetic sample data, but blocks uploads and expires after eight hours. Account login alert emails, administrator roles, and enterprise identity federation are not included in this OTP change. Encrypted persistence does not replace key management, retention policies, backups, or monitoring.

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
