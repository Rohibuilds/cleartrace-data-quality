"""ClearTrace — Persistence and Encryption Test Suite.

Verifies AES-256-GCM encryption at rest, session isolation via AAD,
tamper detection, restart survival, and multi-tenant isolation.
"""

import os
import shutil
import tempfile
from pathlib import Path
import pytest
import pandas as pd
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from cleartrace.audit import SessionManager
from cleartrace.ingest import load_demo_dataset
from cleartrace.persistence import (
    save_encrypted_session,
    load_encrypted_session,
    delete_encrypted_session,
    get_or_create_master_key,
    AuthenticationError,
    SecurityStorageError,
)
from cleartrace.repair import generate_proposal
from cleartrace.scan import scan_dataset


@pytest.fixture
def temp_storage():
    """Create and tear down an isolated temporary directory for test encryption."""
    tmpdir = tempfile.mkdtemp(prefix="ct_persist_test_")
    storage_path = Path(tmpdir)
    yield storage_path
    shutil.rmtree(tmpdir, ignore_errors=True)


def test_key_generation_and_permissions(temp_storage):
    """Test 256-bit AES-GCM key creation and strict filesystem permissions."""
    key_file = temp_storage / "keys" / "master.key"
    key = get_or_create_master_key(key_path=key_file)
    
    assert len(key) == 32  # 256 bits
    assert key_file.exists()
    
    # Check key file mode is 0600 (owner read/write only)
    file_stat = key_file.stat()
    assert (file_stat.st_mode & 0o777) == 0o600

    # Re-reading existing key produces the exact same key bytes
    key2 = get_or_create_master_key(key_path=key_file)
    assert key == key2


def test_session_encryption_not_plaintext(temp_storage):
    """Verify stored session files are strictly encrypted and contain zero plaintext data."""
    df = pd.DataFrame({
        "invoice_id": ["INV-SECRET-999", "INV-TOP-SECRET-001"],
        "client": ["Classified Corp", "Confidential LLC"],
        "recorded_total": [5000.0, 12500.0],
    })
    sm = SessionManager(df, filename="classified_financials.csv")
    session_id = "test_sec_session_123"

    saved_path = save_encrypted_session(session_id, sm, storage_dir=temp_storage)
    assert saved_path.exists()

    # Read raw bytes from disk
    raw_disk_bytes = saved_path.read_bytes()

    # Raw bytes must NOT contain sensitive strings anywhere
    assert b"INV-SECRET-999" not in raw_disk_bytes
    assert b"Classified Corp" not in raw_disk_bytes
    assert b"confidential" not in raw_disk_bytes.lower()
    assert b"classified_financials" not in raw_disk_bytes

    # Must have minimum length: 12-byte nonce + ciphertext + 16-byte tag
    assert len(raw_disk_bytes) > 28


def test_session_rehydration_across_restart(temp_storage):
    """Verify complete state restoration including revisions, working df, and audit logs."""
    df = load_demo_dataset()
    sm = SessionManager(df, filename="demo_data.csv")
    
    # Apply a repair
    findings, _ = scan_dataset(sm.working_df)
    first_actionable = next(f for f in findings if f.action)
    prop = generate_proposal(first_actionable, sm.working_df)
    event = sm.apply_proposal(prop, expected_revision=sm.dataset_revision)
    
    assert sm.dataset_revision == 2
    session_id = "session_restart_test_456"

    # Save to disk
    save_encrypted_session(session_id, sm, storage_dir=temp_storage)

    # Rehydrate into a new instance
    rehydrated = load_encrypted_session(session_id, storage_dir=temp_storage)
    assert rehydrated is not None
    assert rehydrated.filename == "demo_data.csv"
    assert rehydrated.dataset_revision == 2
    assert len(rehydrated.audit_events) == 2  # initial load + 1 repair
    assert rehydrated.audit_events[-1].event_id == event.event_id
    assert len(rehydrated.working_df) == len(sm.working_df)

    # Verify undo works on rehydrated instance
    undo_event = rehydrated.undo_last_action()
    assert undo_event is not None
    assert rehydrated.dataset_revision == 3
    assert len(rehydrated.working_df) == len(sm.original_df)


def test_session_isolation_via_aad(temp_storage):
    """Verify cryptographically that Session B cannot load or tamper with Session A's file."""
    df = load_demo_dataset()
    sm = SessionManager(df, filename="tenant_a.csv")
    session_a = "tenant_session_aaaa1111"
    session_b = "tenant_session_bbbb2222"

    path_a = save_encrypted_session(session_a, sm, storage_dir=temp_storage)

    # Attacker tenant B copies tenant A's encrypted file into their own session slot
    path_b = temp_storage / f"{session_b}.enc"
    shutil.copyfile(path_a, path_b)

    # Tenant B attempts to decrypt it under session B
    # Because session_id is bound as Authenticated Additional Data (AAD), AES-GCM fails with InvalidTag
    with pytest.raises(AuthenticationError) as exc_info:
        load_encrypted_session(session_b, storage_dir=temp_storage)

    assert "integrity check failed" in str(exc_info.value).lower()


def test_tamper_detection(temp_storage):
    """Verify bit-level corruption triggers immediate AuthenticationError."""
    df = load_demo_dataset()
    sm = SessionManager(df, filename="tamper_check.csv")
    session_id = "tamper_test_session"

    saved_path = save_encrypted_session(session_id, sm, storage_dir=temp_storage)
    data = bytearray(saved_path.read_bytes())

    # Flip bits in the middle of ciphertext
    data[len(data) // 2] ^= 0xFF
    saved_path.write_bytes(bytes(data))

    with pytest.raises(AuthenticationError) as exc_info:
        load_encrypted_session(session_id, storage_dir=temp_storage)

    assert "integrity check failed" in str(exc_info.value).lower()


def test_delete_encrypted_session(temp_storage):
    """Test safe deletion of encrypted session files."""
    df = load_demo_dataset()
    sm = SessionManager(df, filename="purge_test.csv")
    session_id = "purge_session"

    saved_path = save_encrypted_session(session_id, sm, storage_dir=temp_storage)
    assert saved_path.exists()

    deleted = delete_encrypted_session(session_id, storage_dir=temp_storage)
    assert deleted is True
    assert not saved_path.exists()

    # Second delete returns False
    assert delete_encrypted_session(session_id, storage_dir=temp_storage) is False


def test_configurable_data_dir_env_var(tmp_path, monkeypatch):
    """Test that CLEARTRACE_DATA_DIR environment variable configures storage paths."""
    from cleartrace.persistence import get_storage_dir, get_key_file, get_session_dir

    custom_data = tmp_path / "custom_railway_mount"
    monkeypatch.setenv("CLEARTRACE_DATA_DIR", str(custom_data))

    assert get_storage_dir() == custom_data
    assert get_key_file() == custom_data / "keys" / "master.key"
    assert get_session_dir() == custom_data / "sessions"


def test_prevent_silent_key_regeneration_when_sessions_exist(tmp_path, monkeypatch):
    """Refuse to silently regenerate encryption key when sessions already exist on disk."""
    from cleartrace.persistence import SecurityStorageError

    # Ensure no environment encryption key is present
    monkeypatch.delenv("CLEARTRACE_MASTER_KEY", raising=False)
    monkeypatch.delenv("CLEARTRACE_ENCRYPTION_KEY", raising=False)

    fake_volume = tmp_path / "railway_data"
    key_path = fake_volume / "keys" / "master.key"
    session_dir = fake_volume / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)

    # Place an orphaned session file (e.g. after a restart where volume is attached but key was not passed)
    fake_session = session_dir / "user_session_12345678.enc"
    fake_session.write_bytes(b"dummy_encrypted_data_blob_32_bytes_long_1234")

    # Calling get_or_create_master_key MUST fail with SecurityStorageError rather than overwriting
    with pytest.raises(SecurityStorageError) as exc_info:
        get_or_create_master_key(key_path=key_path)

    assert "refusing to regenerate a new key to prevent permanent data loss" in str(exc_info.value).lower()


def test_storage_non_writable_raises_security_storage_error(tmp_path):
    """Verify that verify_storage_writable raises SecurityStorageError on read-only directory."""
    from cleartrace.persistence import verify_storage_writable, SecurityStorageError

    ro_dir = tmp_path / "read_only_volume"
    ro_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(ro_dir, 0o500)  # Read + execute only (no write)

    try:
        with pytest.raises(SecurityStorageError) as exc_info:
            verify_storage_writable(ro_dir)
        assert "not writable by process" in str(exc_info.value).lower()
        assert "uid" in str(exc_info.value).lower()
    finally:
        os.chmod(ro_dir, 0o700)  # Restore permissions for cleanup

