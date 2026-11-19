# Security, privacy and reliability requirements

## Threat model
Untrusted CSV upload may be enormous, malformed, differently encoded, include spreadsheet formulas or odd column names, and trigger memory exhaustion. An attacker may attempt injection via cell contents shown in the UI or exported files.

## Core safeguards
1. Local/session processing by default. No unexplained third-party upload.
2. Configurable upload size, row and column limits, with honest user-visible errors.
3. Safe CSV parsing: robust delimiter/encoding handling; no arbitrary object deserialization.
4. Do **not** call `eval`, `exec` or OS shell with user-provided cell text.
5. Escape/encode all untrusted values inserted into HTML; avoid `innerHTML` with raw CSV data.
6. Protect spreadsheet-consumed CSV exports from formula injection for cells starting with dangerous formula syntax (including `=`, `+`, `-`, `@`; also consider leading whitespace/control characters). Define an export policy and explain transformed strings.
7. Avoid exposing secrets, local paths, stack traces or internal implementation in user-facing exceptions.
8. Keep untouched raw input for a session reset, and do not overwrite source files.
9. Validate repair selection server-side against current dataset revision to prevent stale approvals.
10. Minimize persisted information; if session logs are stored, explicitly disclose retention and secure them.
11. No hard-coded API keys; avoid external fonts/CDNs for offline design.
12. Test mobile/desktop and keyboard input, slow renders, repeated clicks and export failures.
13. For a real deployment, inspect Streamlit host security settings and confirm network access/telemetry behavior rather than assuming defaults are private.
14. Do not publish or deploy publicly without the user's explicit authorization.

## Reliability rules
- On failure, keep the working copy consistent; apply mutations transactionally when possible.
- Guard against same action running twice on repeated clicks.
- Keep operations deterministic, revision-scoped and independently testable.
- Validate before/after equivalence where appropriate.
- Use real progress/errors; no invented “100% secure”, “zero risk”, “AI confidence 99%”, or all-features-complete claims.

## Privacy copy for the UI
Use cautious wording: **“Designed for session-local processing; review deployment settings before uploading sensitive files.”** Only display stronger statements after the implementation has been inspected and tested.
