#!/bin/sh
set -e

# ==============================================================================
# ClearTrace — Production Container Entrypoint
# Guarantees non-root execution (UID 10001) while resolving Railway volume
# permissions at /data.
# ==============================================================================

DATA_DIR="${CLEARTRACE_DATA_DIR:-/data}"

# If launched as root (UID 0), adjust persistent volume ownership and drop privileges
if [ "$(id -u)" = "0" ]; then
    # Create persistent subdirectories if not yet present
    mkdir -p "$DATA_DIR/keys" "$DATA_DIR/sessions"

    # Ensure the non-root cleartrace user (UID 10001) owns the volume
    chown -R cleartrace:cleartrace "$DATA_DIR"
    chmod 700 "$DATA_DIR" "$DATA_DIR/keys" "$DATA_DIR/sessions"

    # Execute the requested command as unprivileged cleartrace user via gosu
    exec gosu cleartrace "$@"
fi

# Fallback: if already running as non-root user, execute directly
exec "$@"
