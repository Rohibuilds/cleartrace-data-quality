"""Shared local test defaults; production auth is exercised by focused OTP tests."""

import pytest


@pytest.fixture(autouse=True)
def local_api_test_mode(monkeypatch, tmp_path):
    """Keep API behavior tests independent of production email delivery settings."""
    monkeypatch.setenv("CLEARTRACE_AUTH_ENABLED", "false")
    monkeypatch.setenv("CLEARTRACE_DATA_DIR", str(tmp_path / "cleartrace-test-data"))
