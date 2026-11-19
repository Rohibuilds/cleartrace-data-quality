# Architecture and suggested file plan

## Historically described prototype
A local **Python + Streamlit + Pandas** prototype was previously described. Its original files are not attached, and this archive does not assume its implementation is validated. Before coding:
1. Locate and open the real `app.py` / `requirements.txt` from the earlier prototype if available.
2. Install its dependencies, start it, and record actual output/bugs.
3. Preserve working functionality and regression-test before any refactor.

## Suggested clean architecture — not an existing implementation
```
cleartrace/
├── app.py                     # Streamlit UI entry
├── requirements.txt
├── cleartrace/
│   ├── ingest.py              # CSV validation and input boundaries
│   ├── scan.py                # deterministic detection
│   ├── suggestions.py         # proposed non-mutating repairs
│   ├── apply.py               # explicit-approval operations
│   ├── audit.py               # revision-based event tracking
│   ├── export.py              # clean CSV/findings/audit downloads
│   └── metrics.py             # defined dashboard statistics
├── ui/
│   ├── components.py          # safe interface components
│   └── styles.css             # optional design tokens
├── design_reference/          # Antigravity-generated HTML/CSS/JS (visual)
├── tests/
│   ├── test_ingest.py
│   ├── test_scan.py
│   ├── test_repair.py
│   ├── test_audit.py
│   └── test_export_security.py
└── README.md
```
Use this only after inspecting original source. Do not overwrite or replace a working project merely to match a folder diagram.

## Streamlit versus standalone HTML
Antigravity's static HTML/CSS/JS is a **design reference**, not automatically a Streamlit application. Integration options:
- Port reusable layout tokens and components to native Streamlit UI, preserving Python state.
- Build a tested custom Streamlit component if bidirectional JS interaction is essential.
- Migrate to a Python API + HTML frontend only if justified, scoped and explicitly approved; this increases implementation and security work.

Never connect fake onClick handlers to toast “Applied” unless a real authenticated data operation completed. Avoid embedding untrusted CSV cell content in unsafe HTML.

## UI ↔ engine contract (proposed)
- `load_dataset(file_bytes, parsing_options) -> session metadata, immutable baseline, working table`.
- `scan(working_revision, settings) -> findings, metrics`.
- `preview(proposal_id, revision) -> diff, risk`.
- `approve_and_apply(proposal_id, expected_revision) -> event, new_revision`.
- `undo(event_id, expected_revision) -> event, new_revision`.
- `reset() -> baseline working table, new_revision, audit reset event`.
- `export(kind) -> safe bytes + mime type + filename`.

Keep operations idempotent or guarded against replay, and never pretend an API contract is already implemented just because it appears in these docs.
