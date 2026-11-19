#!/usr/bin/env python3
"""ClearTrace — Application Runner.

Usage:
    python3 run.py             # Launches the production FastAPI PWA Server (Port 8000)
    python3 run.py --streamlit # Launches the Streamlit Studio interface (Port 8501)
    python3 run.py --test      # Runs the complete pytest test suite
"""

import sys
import subprocess
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(BASE_DIR, ".venv", "bin", "python")
VENV_UVICORN = os.path.join(BASE_DIR, ".venv", "bin", "uvicorn")
VENV_STREAMLIT = os.path.join(BASE_DIR, ".venv", "bin", "streamlit")
VENV_PYTEST = os.path.join(BASE_DIR, ".venv", "bin", "pytest")

# Fallback to system python if venv binary not directly present
python_bin = VENV_PYTHON if os.path.exists(VENV_PYTHON) else sys.executable


def run_fastapi():
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    reload_flag = os.environ.get("CLEARTRACE_DEV_RELOAD", "false").lower() in ("true", "1")
    print("=" * 60)
    print("  ClearTrace — Data Quality & Autonomous Repair Studio")
    print("  Mode: Production FastAPI + PWA Single Page Application")
    print(f"  Bind Address: {host}:{port}")
    print(f"  Local URL:    http://{host}:{port}")
    print(f"  API Docs:     http://{host}:{port}/docs")
    print("=" * 60)
    env = os.environ.copy()
    env["PYTHONPATH"] = BASE_DIR
    cmd = [python_bin, "-m", "uvicorn", "server:app", "--host", host, "--port", str(port), "--workers", "1"]
    if reload_flag:
        cmd.append("--reload")
    subprocess.run(cmd, env=env)


def run_streamlit():
    print("=" * 60)
    print("  ClearTrace — Streamlit Companion Studio")
    print("  Local URL:  http://127.0.0.1:8501")
    print("=" * 60)
    env = os.environ.copy()
    env["PYTHONPATH"] = BASE_DIR
    cmd = [python_bin, "-m", "streamlit", "run", "app.py", "--server.port", "8501"]
    subprocess.run(cmd, env=env)


def run_tests():
    print("=" * 60)
    print("  Running ClearTrace Automated Test Suite (pytest)")
    print("=" * 60)
    env = os.environ.copy()
    env["PYTHONPATH"] = BASE_DIR
    cmd = [python_bin, "-m", "pytest", "-v", "tests/"]
    subprocess.run(cmd, env=env)


if __name__ == "__main__":
    if "--streamlit" in sys.argv:
        run_streamlit()
    elif "--test" in sys.argv:
        run_tests()
    else:
        run_fastapi()
