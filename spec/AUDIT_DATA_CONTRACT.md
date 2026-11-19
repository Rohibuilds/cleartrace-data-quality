# Data, state and audit contract

## Required state model (proposed)
- `original_df`: untouched snapshot of uploaded CSV.
- `working_df`: revised version after approved mutations.
- `dataset_revision`: monotonic counter incremented after each mutation/undo/reset.
- `scan_settings`: columns and detection parameters.
- `findings`: scan-derived issue records tied to a revision.
- `proposals`: candidate mutations, with preview and approval state.
- `audit_events`: append-only logical history for this session.
- `undo_stack`: reversible change snapshots or invertible operations.
- `last_scan_revision`: revision whose findings were most recently computed.

## Event fields
`event_id`, `timestamp_utc`, `dataset_revision_before`, `dataset_revision_after`, `actor`, `decision`, `rule_id`, `target_row_ids`, `target_columns`, `before`, `after`, `reason`, `approval_reference`, `result`, `undo_of`.

- Actor can be `scanner` for detection, `system` for proposal, `user` for approval, and `engine` for successful execution.
- Separate **approval** events from **application** events.
- One approved batch may contain multiple row-level changes; ensure each modified cell is recoverable.
- Avoid placing user data in error logs outside the session.
- Real timestamps must come from application execution, never mock history, when running production code.

## Example event (illustrative only)
```json
{
  "event_id": "evt-demo-001",
  "timestamp_utc": "EXAMPLE_ONLY",
  "actor": "user",
  "decision": "approved",
  "rule_id": "trim-whitespace",
  "target_row_ids": ["row-3"],
  "target_columns": ["city"],
  "before": " Bengaluru ",
  "after": "Bengaluru",
  "reason": "Leading/trailing whitespace",
  "result": "pending_application"
}
```

## UI status vocabulary
- **Unscanned:** no scan on current revision.
- **Detected:** rule found an issue.
- **Proposed:** preview exists, no edit performed.
- **Approved:** a person permitted the change.
- **Applied:** mutation succeeded on working copy.
- **Verified:** a follow-up scan supports the expected result.
- **Undone:** previous application reversed.
- **Needs review / Unable to verify:** ambiguity or failure, not success.

## Design reminder
If Antigravity builds purely static HTML/JS, every table value must be marked **sample content** and cannot be treated as data from a real scan until integrated with the Python engine.
