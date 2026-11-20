"""ClearTrace — Secure Encrypted Persistence Layer.

Provides local-first, authenticated AES-256-GCM encryption for stored datasets,
revisions, Time Machine snapshots, and audit history.
Guarantees:
1. Datasets, repairs, and audit trails survive application restarts.
2. Sensitive data at rest is encrypted with military-grade AES-256-GCM (NIST SP 800-38D).
3. Session isolation: each session ciphertext is cryptographically bound to its unique
   session ID via Authenticated Additional Data (AAD), preventing cross-user session tampering.
4. Secure key management: master key stored in restricted keyfiles (0600) or environment variables.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

from cleartrace.audit import SessionManager
from cleartrace.models import AuditEvent, MathRuleConfig
from cleartrace.timemachine import TimeMachine, RevisionSnapshot

logger = logging.getLogger("cleartrace.persistence")

def get_storage_dir() -> Path:
    """Return the base storage directory, configurable via environment variable."""
    env_dir = os.environ.get("CLEARTRACE_DATA_DIR") or os.environ.get("CLEARTRACE_STORAGE_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(".data")


def get_key_file() -> Path:
    """Return path to master key file."""
    return get_storage_dir() / "keys" / "master.key"


def get_session_dir() -> Path:
    """Return path to encrypted session storage directory."""
    return get_storage_dir() / "sessions"


DEFAULT_STORAGE_DIR = get_storage_dir()
DEFAULT_KEY_FILE = get_key_file()
DEFAULT_SESSION_DIR = get_session_dir()


class SecurityStorageError(Exception):
    """Raised when cryptographic or persistence operations fail."""
    pass


class AuthenticationError(SecurityStorageError):
    """Raised when session authentication or decryption integrity fails."""
    pass


SAFE_SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]{8,64}$")


def validate_session_id(session_id: str) -> None:
    """Validate that session_id contains only safe identifier characters (8-64 chars)."""
    if not isinstance(session_id, str) or not SAFE_SESSION_ID_PATTERN.match(session_id):
        raise SecurityStorageError(f"Invalid or unsafe session identifier: {session_id!r}")


def verify_storage_writable(directory: Path) -> None:
    """Verify that storage directory exists and has write permissions for the current UID."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        test_probe = directory / ".write_probe"
        test_probe.touch()
        test_probe.unlink()
    except (OSError, PermissionError) as exc:
        uid = os.geteuid() if hasattr(os, "geteuid") else "unknown"
        raise SecurityStorageError(
            f"Persistent storage directory '{directory}' is not writable by process (UID {uid}): {exc}. "
            "If deployed with a persistent volume (e.g. Railway /data), ensure the mount point is owned "
            "by the non-root user (UID 10001) with 0700 permissions."
        ) from exc


def get_or_create_master_key(key_path: Optional[Path] = None) -> bytes:
    """Retrieve or generate the 256-bit AES-GCM master encryption key.
    
    Priority:
    1. CLEARTRACE_ENCRYPTION_KEY or CLEARTRACE_MASTER_KEY environment variable (urlsafe base64 or 64-char hex).
    2. Local key file with restricted 0600 permissions.
    3. Fail-safe guard: If session directory already contains encrypted files, refuses to generate a new key.
    4. Generate fresh 256-bit key for a newly initialized data store.
    """
    env_key = os.environ.get("CLEARTRACE_ENCRYPTION_KEY") or os.environ.get("CLEARTRACE_MASTER_KEY")
    if env_key:
        try:
            if len(env_key) == 64:  # Hex representation
                return bytes.fromhex(env_key)
            decoded = base64.urlsafe_b64decode(env_key.encode("utf-8"))
            if len(decoded) == 32:
                return decoded
        except (ValueError, binascii.Error) as err:
            logger.debug("Failed parsing env encryption key: %s", err)

    path = key_path or get_key_file()
    if path.exists():
        raw = path.read_bytes().strip()
        if len(raw) == 32:
            return raw
        try:
            decoded = base64.urlsafe_b64decode(raw)
            if len(decoded) == 32:
                return decoded
        except (ValueError, binascii.Error) as err:
            logger.debug("Failed decoding key file: %s", err)

    # CRITICAL DATA LOSS PREVENTION:
    # If key file is absent and no environment key is supplied, check if existing
    # encrypted sessions exist in the session directory.
    # Refuse to silently overwrite or generate a new key that would render existing sessions permanently unrecoverable.
    session_dir = (path.parent.parent / "sessions") if key_path else get_session_dir()
    if session_dir.exists():
        existing_enc_files = list(session_dir.glob("*.enc"))
        if existing_enc_files:
            raise SecurityStorageError(
                f"Existing encrypted session files ({len(existing_enc_files)} found) detected in '{session_dir}', "
                "but master encryption key is missing from environment and keyfile. "
                "Refusing to regenerate a new key to prevent permanent data loss. "
                "Please configure CLEARTRACE_MASTER_KEY or restore the master keyfile."
            )

    # Verify directory write permissions for current process (UID) before key generation
    verify_storage_writable(path.parent)

    # Generate fresh 256-bit key for clean initialization
    new_key = AESGCM.generate_key(bit_length=256)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Set directory permissions to 0700
    try:
        os.chmod(path.parent, 0o700)
    except OSError as err:
        logger.debug("Could not chmod key directory: %s", err)

    # Write key with 0600 permissions
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(base64.urlsafe_b64encode(new_key))

    return new_key


def _serialize_session_state(sm: SessionManager) -> bytes:
    """Serialize SessionManager state into canonical JSON bytes."""
    state = {
        "filename": sm.filename,
        "document_format": sm.document_format,
        "dataset_revision": sm.dataset_revision,
        "provenance_map": {str(k): v for k, v in sm.provenance_map.items()},
        "warnings": sm.warnings,
        "original_df": sm.original_df.to_dict(orient="split"),
        "working_df": sm.working_df.to_dict(orient="split"),
        "audit_events": [
            {
                "event_id": e.event_id,
                "timestamp_utc": e.timestamp_utc,
                "dataset_revision_before": e.dataset_revision_before,
                "dataset_revision_after": e.dataset_revision_after,
                "actor": e.actor,
                "decision": e.decision,
                "rule_id": e.rule_id,
                "target_columns": e.target_columns,
                "target_rows": e.target_rows,
                "before_summary": e.before_summary,
                "after_summary": e.after_summary,
                "reason": e.reason,
                "items_changed": e.items_changed,
                "undo_of": e.undo_of,
            }
            for e in sm.audit_events
        ],
        "undo_stack": [
            (prev_df.to_dict(orient="split"), event_id, rule_id)
            for prev_df, event_id, rule_id in sm._undo_stack
        ],
        "time_machine_snapshots": [
            {
                "revision": snap.revision,
                "timestamp_utc": snap.timestamp_utc,
                "action": snap.action,
                "description": snap.description,
                "row_count": snap.row_count,
                "col_count": snap.col_count,
                "content_hash": snap.content_hash,
                "frame": snap.frame.to_dict(orient="split"),
            }
            for snap in sm.time_machine.snapshots.values()
        ],
        "custom_math_rules": [
            {
                "rule_id": r.rule_id,
                "rule_type": r.rule_type,
                "target_column": r.target_column,
                "expression": r.expression,
                "addend_columns": r.addend_columns,
                "part_column": r.part_column,
                "total_column": r.total_column,
                "old_column": r.old_column,
                "new_column": r.new_column,
                "constraint_type": r.constraint_type,
                "constraint_value": r.constraint_value,
                "tolerance": r.tolerance,
                "decimal_places": r.decimal_places,
                "rounding_mode": r.rounding_mode,
                "severity": r.severity,
                "description": r.description,
            }
            for r in getattr(sm, "custom_math_rules", [])
        ],
        "rejected_findings": sorted(getattr(sm, "rejected_findings", set())),
    }
    return json.dumps(state, ensure_ascii=False).encode("utf-8")


def _deserialize_session_state(data_bytes: bytes) -> SessionManager:
    """Rehydrate a SessionManager instance from serialized state."""
    state = json.loads(data_bytes.decode("utf-8"))

    orig_df = pd.DataFrame(**state["original_df"])
    working_df = pd.DataFrame(**state["working_df"])
    prov_map = {int(k): v for k, v in state.get("provenance_map", {}).items()}

    # Initialize SessionManager bypassing default initial audit event creation
    sm = SessionManager.__new__(SessionManager)
    sm.filename = state["filename"]
    sm.document_format = state.get("document_format", "csv")
    sm.provenance_map = prov_map
    sm.warnings = state.get("warnings", [])
    sm.original_df = orig_df
    sm.working_df = working_df
    sm.dataset_revision = state["dataset_revision"]
    sm.math_findings = []
    sm._evidence_index = None

    # Reconstruct audit events
    sm.audit_events = [
        AuditEvent(
            event_id=e["event_id"],
            timestamp_utc=e["timestamp_utc"],
            dataset_revision_before=e["dataset_revision_before"],
            dataset_revision_after=e["dataset_revision_after"],
            actor=e["actor"],
            decision=e["decision"],
            rule_id=e["rule_id"],
            target_columns=e["target_columns"],
            target_rows=e["target_rows"],
            before_summary=e["before_summary"],
            after_summary=e["after_summary"],
            reason=e["reason"],
            items_changed=e["items_changed"],
            undo_of=e.get("undo_of"),
        )
        for e in state.get("audit_events", [])
    ]

    # Reconstruct undo stack
    sm._undo_stack = [
        (pd.DataFrame(**df_dict), event_id, rule_id)
        for df_dict, event_id, rule_id in state.get("undo_stack", [])
    ]

    # Reconstruct TimeMachine
    tm = TimeMachine.__new__(TimeMachine)
    tm.snapshots = {
        s["revision"]: RevisionSnapshot(
            revision=s["revision"],
            timestamp_utc=s["timestamp_utc"],
            action=s["action"],
            description=s["description"],
            row_count=s.get("row_count", len(s["frame"]["data"])),
            col_count=s.get("col_count", len(s["frame"]["columns"])),
            content_hash=s.get("content_hash", ""),
            frame=pd.DataFrame(**s["frame"]),
        )
        for s in state.get("time_machine_snapshots", [])
    }
    sm.time_machine = tm
    sm.custom_math_rules = [
        MathRuleConfig(**r) for r in state.get("custom_math_rules", [])
    ]
    sm.rejected_findings = set(state.get("rejected_findings", []))

    return sm


def save_encrypted_session(
    session_id: str,
    sm: SessionManager,
    storage_dir: Optional[Path] = None,
    master_key: Optional[bytes] = None,
) -> Path:
    """Encrypt and atomically persist session state to disk using AES-256-GCM.
    
    Session ID is passed as Authenticated Additional Data (AAD) to ensure cryptographic
    ownership binding.
    """
    validate_session_id(session_id)
    directory = storage_dir or get_session_dir()
    verify_storage_writable(directory)
    key = master_key or get_or_create_master_key()
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass

    target_path = directory / f"{session_id}.enc"

    # Serialize and encrypt
    plaintext = _serialize_session_state(sm)
    nonce = os.urandom(12)  # 96-bit random nonce
    aesgcm = AESGCM(key)
    # Bind session_id as AAD
    aad = session_id.encode("utf-8")
    ciphertext = aesgcm.encrypt(nonce, plaintext, aad)

    # Atomic write via tempfile in the same directory
    with tempfile.NamedTemporaryFile(dir=directory, delete=False) as tf:
        tf.write(nonce + ciphertext)
        temp_name = tf.name

    os.chmod(temp_name, 0o600)
    os.replace(temp_name, target_path)
    return target_path


def load_encrypted_session(
    session_id: str,
    storage_dir: Optional[Path] = None,
    master_key: Optional[bytes] = None,
) -> Optional[SessionManager]:
    """Load and decrypt session state from disk using AES-256-GCM.
    
    Verifies AAD matching the requested session_id. Raises AuthenticationError
    if the authentication tag is invalid or tampered with.
    """
    validate_session_id(session_id)
    key = master_key or get_or_create_master_key()
    directory = storage_dir or get_session_dir()
    target_path = directory / f"{session_id}.enc"

    if not target_path.exists():
        return None

    encrypted_blob = target_path.read_bytes()
    if len(encrypted_blob) < 28:  # 12 nonce + 16 auth tag minimum
        raise SecurityStorageError(f"Corrupted or truncated session file: {target_path}")

    nonce = encrypted_blob[:12]
    ciphertext = encrypted_blob[12:]

    aesgcm = AESGCM(key)
    aad = session_id.encode("utf-8")

    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise AuthenticationError(
            f"Decryption integrity check failed for session '{session_id}'. "
            "Data may have been tampered with, corrupted, or accessed with an invalid session token."
        ) from exc

    return _deserialize_session_state(plaintext)


def delete_encrypted_session(
    session_id: str,
    storage_dir: Optional[Path] = None,
) -> bool:
    """Securely purge encrypted session file from storage."""
    validate_session_id(session_id)
    directory = storage_dir or get_session_dir()
    target_path = directory / f"{session_id}.enc"
    if target_path.exists():
        target_path.unlink()
        return True
    return False
