# ==============================================================================
# ClearTrace — Production Multi-Stage Container Image
# Targets: Railway, Render, Fly.io, Google Cloud Run
# Base: Python 3.11-slim (Hardened, Non-Root execution with UID 10001)
# ==============================================================================

FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies for C-extensions (cryptography, reportlab, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Final Minimal Runtime Stage ───────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Security & Python Optimization Environment Variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000 \
    HOST=0.0.0.0 \
    CLEARTRACE_DATA_DIR=/data \
    CLEARTRACE_DEMO_MODE=true

WORKDIR /app

# Install gosu for secure privilege dropping from root to UID 10001
RUN apt-get update && apt-get install -y --no-install-recommends \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Copy installed python wheels from builder
COPY --from=builder /install /usr/local

# Create non-root system user and persistent storage mount directory
RUN groupadd -g 10001 cleartrace && \
    useradd -u 10001 -g cleartrace -s /bin/bash -m cleartrace && \
    mkdir -p /data /app && \
    chown -R cleartrace:cleartrace /data /app

# Copy application source code, entrypoint, and static PWA assets
COPY --chown=cleartrace:cleartrace cleartrace/ /app/cleartrace/
COPY --chown=cleartrace:cleartrace static/ /app/static/
COPY --chown=cleartrace:cleartrace samples/ /app/samples/
COPY --chown=cleartrace:cleartrace server.py /app/server.py
COPY --chown=cleartrace:cleartrace run.py /app/run.py
COPY --chown=cleartrace:cleartrace docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Declare volume mount point for persistent session encryption

# Platform dynamic port exposure
EXPOSE 8000

# Container healthcheck probe (zero external dependencies)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request, os; port = os.environ.get('PORT', '8000'); urllib.request.urlopen(f'http://127.0.0.1:{port}/health')" || exit 1

# Production entrypoint drops root privileges to UID 10001 after securing /data
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python3", "server.py"]
