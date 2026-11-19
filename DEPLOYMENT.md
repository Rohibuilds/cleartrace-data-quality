# ClearTrace — Production Deployment & Operations Guide

> **Target Platform:** Railway (Primary) · Render / Docker / Cloud Run (Alternative)  
> **Architecture:** FastAPI + Uvicorn + AES-256-GCM AEAD Encrypted Persistence + Vanilla ES6 PWA  
> **Runtime Target:** Python 3.11 / 3.12 (Debian Slim, Non-Root UID 10001)

---

## 1. Architecture & Platform Overview

ClearTrace is containerized as a standalone, non-root web service serving both the REST API and the installable Progressive Web App (PWA) under a unified same-origin HTTPS domain.

```
                          ┌──────────────────────────────────────┐
                          │    Browser / iPhone Safari (PWA)     │
                          └──────────────────┬───────────────────┘
                                             │ HTTPS
                                             ▼
                          ┌──────────────────────────────────────┐
                          │   Railway Edge Router / SSL Proxy    │
                          │   (terminates SSL, injects $PORT)    │
                          └──────────────────┬───────────────────┘
                                             │ HTTP (0.0.0.0:$PORT)
                                             ▼
┌────────────────────────────────────────────────────────────────────────┐
│ ClearTrace Container (python:3.11-slim, UID 10001)                    │
│                                                                        │
│   FastAPI + Uvicorn (Single Worker, Async Event Loop)                 │
│   ├── SecurityHeadersMiddleware (CSP, nosniff, DENY, strict-origin)    │
│   ├── RateLimitingMiddleware (180 req/min per IP sliding window)       │
│   ├── SessionIsolationMiddleware (AES-256-GCM AEAD + AAD binding)      │
│   ├── Lightweight Container Probe (/health)                            │
│   ├── BM25 Evidence Retrieval Engine (Deterministic Fallback)          │
│   └── Mathematical Validation & Autonomous Repair Engine               │
└────────────────────────────────────┬───────────────────────────────────┘
                                     │ Persistent I/O
                                     ▼
                          ┌──────────────────────────────────────┐
                          │ Railway Persistent Volume (/data)     │
                          │ ├── /data/keys/master.key (0600)     │
                          │ └── /data/sessions/<id>.enc (0600)   │
                          └──────────────────────────────────────┘
```

---

## 2. Pre-Deployment Configuration Checklist

Verify all deployment assets prepared in the repository:

| File | Status | Purpose |
|:-----|:------:|:--------|
| `Dockerfile` | ✅ Ready | Multi-stage build (`python:3.11-slim`), non-root UID 10001, volume `/data` |
| `docker-entrypoint.sh` | ✅ Ready | Fixes Railway volume permissions and drops root to UID 10001 via `gosu` |
| `railway.json` | ✅ Ready | Railway build & deploy spec, healthcheck `/health`, restart policy |
| `Procfile` | ✅ Ready | Single-line process specification (`web: python3 server.py`) |
| `.dockerignore` | ✅ Ready | Excludes `.venv`, `.data`, local keys, test caches, and private uploads |
| `.gitignore` | ✅ Ready | Prevents committing encryption keys, sessions, or credentials |
| `.env.example` | ✅ Ready | Documents all environment variables without secrets |
| `requirements.txt` | ✅ Ready | Python 3.11/3.12-compatible pinned dependencies |

---

## 3. Local Environment Disclosure & Railway Build Validation

> [!NOTE]
> **Local Environment Status:** The local macOS development machine does not have the Docker daemon / CLI installed.
> Railway executes container builds remotely on Linux build servers using BuildKit.

### Exact Railway Build Validation Steps

1. **Deploy to Railway:** When the repository is connected to Railway, Railway triggers a Dockerfile build on a dedicated Linux build machine.
2. **Inspect Build Logs:**
   - In Railway Web Console, navigate to your service $\rightarrow$ **Deployments** $\rightarrow$ select active deployment $\rightarrow$ click **Build Logs**.
   - Confirm lines:
     ```text
     Step: FROM python:3.11-slim AS builder
     Step: RUN pip install --no-cache-dir --prefix=/install -r requirements.txt
     Step: FROM python:3.11-slim AS runtime
     Step: RUN apt-get install -y --no-install-recommends gosu
     Step: COPY --chown=cleartrace:cleartrace ...
     Step: ENTRYPOINT ["/app/docker-entrypoint.sh"]
     Successfully tagged ...
     ```
3. **Verify Container Runtime:**
   - Navigate to **Deployments** $\rightarrow$ **Deploy Logs**.
   - Look for the startup banner:
     ```text
     [*] ClearTrace Production Server starting on 0.0.0.0:<PORT>
     INFO: Uvicorn running on http://0.0.0.0:<PORT> (Press CTRL+C to quit)
     ```
4. **Local Build Alternative (if Docker/Colima is installed later):**
   ```bash
   docker build -t cleartrace:2.2.0 .
   docker run -p 8000:8000 -e CLEARTRACE_MASTER_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')" cleartrace:2.2.0
   ```

---

## 4. Railway Volume Permissions (UID 10001 & gosu)

Railway persistent volumes mounted to `/data` may initially be owned by `root:root` with mode 0755.

To prevent permission crashes (`PermissionError: [Errno 13]`) while preserving strict non-root security:
1. `docker-entrypoint.sh` executes initially as root (UID 0).
2. It creates `/data/keys` and `/data/sessions` and runs `chown -R cleartrace:cleartrace /data && chmod 700 /data /data/keys /data/sessions`.
3. It immediately invokes `exec gosu cleartrace "$@"`, permanently dropping all root privileges before Python and Uvicorn start.
4. Python and Uvicorn execute **100% as unprivileged user `cleartrace` (UID 10001)**.
5. In `cleartrace/persistence.py`, `verify_storage_writable` tests filesystem access on startup and reports an explicit error with process UID if non-writable.

---

## 5. Supported Document Format Matrix

| Format | Extension | Engine | Status | Security Behavior |
|:-------|:----------|:-------|:------:|:------------------|
| **Comma-Separated** | `.csv` | `csv` + `pandas` | ✅ Full Support | Sniffer delimiter detection; formula injection prefix sanitization |
| **Tab-Separated** | `.tsv` | `csv` + `pandas` | ✅ Full Support | Automatic tab delimiter handling; provenance mapping |
| **Modern Excel** | `.xlsx`, `.xlsm` | `openpyxl` | ✅ Full Support | Macro rejection (`vbaproject.bin`); formula text preserved without execution; 30 MB uncompressed limit |
| **Text-Based PDF** | `.pdf` | `pdfplumber` | ✅ Full Support | Tabular extraction with page/table/row provenance; 15-page limit |
| **Legacy Excel** | `.xls` | None (BIFF8) | ❌ **Rejected** | Explicit 400 error advising user to convert to `.xlsx` or `.csv`. Prevents binary parser vulnerabilities |

---

## 6. Step-by-Step Railway Deployment Guide

### Option A: Railway Web Dashboard (Recommended)

#### Step 1: Create a Railway Project
1. Log in to [Railway Dashboard](https://railway.com/dashboard).
2. Click **New Project** $\rightarrow$ **Deploy from GitHub repo**.
3. Select your ClearTrace repository.
4. Railway will automatically detect the `Dockerfile` and `railway.json`.

#### Step 2: Configure Environment Variables
In your service dashboard, navigate to **Variables** $\rightarrow$ **Raw Editor**, and add:

```bash
# Network binding (automatically assigned by Railway)
HOST=0.0.0.0

# Persistent volume mount path (must match attached volume)
CLEARTRACE_DATA_DIR=/data

# Master AES-256-GCM Encryption Key (64-char hex)
# Generate locally using: python3 -c "import secrets; print(secrets.token_hex(32))"
CLEARTRACE_MASTER_KEY=<YOUR_GENERATED_64_CHAR_HEX_KEY>

# Access Mode: true for open hackathon evaluation; false for enterprise lockdown
CLEARTRACE_DEMO_MODE=true

# High-Entropy Access Token (never use hardcoded/predictable passwords)
# Generate locally using: python3 -c "import secrets; print(secrets.token_urlsafe(32))"
# Note: Tokens in URL query strings (?token=...) are strictly rejected (OWASP ASVS / CWE-598).
# Supply tokens via 'Authorization: Bearer <token>' or 'X-Access-Token: <token>' headers only.
CLEARTRACE_ACCESS_TOKEN=<YOUR_GENERATED_STRONG_ACCESS_TOKEN>

# Upload Limit in MB (supported: CSV, TSV, XLSX, PDF; legacy .xls rejected)
CLEARTRACE_MAX_UPLOAD_MB=15
```

> [!IMPORTANT]
> **Action Required by User:** Generate `CLEARTRACE_MASTER_KEY` and `CLEARTRACE_ACCESS_TOKEN` using the commands above and store them in a secure password manager.

#### Step 3: Attach Railway Persistent Volume
1. In the service view, click **+ Add Volume** (or go to **Settings** $\rightarrow$ **Volumes**).
2. Set the **Mount Path** to: `/data`.
3. Save. The volume will be attached to `/data` across deployments and restarts.

#### Step 4: Generate Public HTTPS Domain
1. In your service settings, navigate to **Networking** $\rightarrow$ **Public Networking**.
2. Click **Generate Domain**.
3. Railway assigns an HTTPS domain: `https://<your-service>.up.railway.app`.

---

### Option B: Railway CLI Deployment

```bash
# 1. Install Railway CLI (macOS)
brew install railway

# 2. Authenticate
railway login

# 3. Initialize project
railway init --name cleartrace-prod

# 4. Attach persistent volume at /data
railway volume add --mount-path /data

# 5. Set environment variables with securely generated secrets
MASTER_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
ACCESS_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"

railway variables set \
  HOST="0.0.0.0" \
  CLEARTRACE_DATA_DIR="/data" \
  CLEARTRACE_DEMO_MODE="true" \
  CLEARTRACE_MAX_UPLOAD_MB="15" \
  CLEARTRACE_MASTER_KEY="$MASTER_KEY" \
  CLEARTRACE_ACCESS_TOKEN="$ACCESS_TOKEN"

# 6. Deploy code
railway up

# 7. Generate public domain
railway domain
```

---

## 7. Verification & Health Monitoring

### 1. Automated Health Check
```bash
# Public health endpoint (lightweight, zero session allocation, no secret leakage)
curl -s -i https://<your-service>.up.railway.app/health
```

Expected Response:
```http
HTTP/2 200
content-type: application/json

{
  "status": "healthy",
  "service": "ClearTrace Data Quality Engine",
  "version": "2.2.0",
  "storage": "ready",
  "llm": "direct-evidence"
}
```

### 2. Verify Session Encryption & Volume Persistence
1. Open `https://<your-service>.up.railway.app` on phone or desktop.
2. Load demo dataset or upload a CSV/TSV/XLSX.
3. Apply a repair proposal (e.g. `DUP-001` or `INV-002`).
4. Trigger a restart in Railway (**Settings** $\rightarrow$ **Restart Service**).
5. Refresh the browser:
   - Dataset revision remains restored.
   - Audit event history is intact.
   - Quality score reflects approved repairs.

---

## 8. Rollback & Troubleshooting

### Instant Rollback
1. Go to Railway Dashboard $\rightarrow$ **Deployments**.
2. Select any previously healthy deployment.
3. Click the three dots $\rightarrow$ **Rollback to this deployment**.

### Common Symptoms and Solutions

| Symptom | Probable Cause | Immediate Remediation |
|:--------|:---------------|:----------------------|
| **502 Bad Gateway** | Application failed to bind to `$PORT` or died on startup | Check logs; verify `python3 server.py` binds to `0.0.0.0:$PORT`. |
| **503 Service Unavailable** | Persistent volume not mounted | Confirm volume mount path is `/data` and service has volume attached. |
| **401 Unauthorized on Upload** | `CLEARTRACE_DEMO_MODE=false` without access token | Supply `Authorization: Bearer <CLEARTRACE_ACCESS_TOKEN>` header. (Query param `?token=` is rejected). |
| **400 Bad Request on .xls** | Legacy Excel 97-2003 uploaded | Save file as modern `.xlsx` or `.csv` and re-upload. |
| **429 Too Many Requests** | Rate limit exceeded (>180 requests/min per IP) | Wait 60 seconds. Rate limiter resets sliding window automatically. |
| **SecurityStorageError: Refusing to regenerate key** | Master key missing while session files exist | Set `CLEARTRACE_MASTER_KEY` environment variable in Railway Dashboard. |

---

## 9. Cost & Resource Projections

| Resource | Configuration | Railway Hobby Tier Cost |
|:---------|:--------------|:------------------------|
| **Web Service** | 1 vCPU, 512 MB – 1 GB RAM (Python 3.11) | ~$3.00 – $4.50 / month |
| **Persistent Volume** | 1 GB SSD Volume at `/data` | ~$0.25 / month |
| **Total Estimated Cost** | Base usage for evaluation | **~$5.00 / month** (within Railway $5 monthly credit) |
