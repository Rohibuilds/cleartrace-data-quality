# Complete functional requirements

## User journey (must be truly executable)

**Upload → Preview → Scan → Understand → Propose → Review → Approve/Reject → Apply → Rescan → Undo/Reset → Export.**

### FR-01 — upload and dataset session
- Accept CSV (no hidden cloud upload).
- Show file name, size, row/column counts, headers, preview.
- Provide a synthetic demo dataset for an immediate judge demonstration.
- Reject empty, malformed, unsupported or oversized inputs with friendly safe messages.
- Handle encoding/delimiters/quoted newlines carefully. Warn when parsing assumptions are made.
- Retain untouched original data alongside a working copy.
- Provide a clear **Session only** indicator; do not promise zero storage without implementation proof.

### FR-02 — scan for quality issues
- Missing/null/empty/whitespace-only values; optionally user-approved missing tokens.
- Exact duplicate rows; preserve locations and originals.
- Leading/trailing whitespace and inconsistent formatting.
- Category variants (e.g. `New York`, `new york`, `NEW YORK`) as candidate equivalences.
- Invalid date values, ambiguous date formats and invalid numeric values in typed columns.
- Numeric outliers using a documented rule, e.g. configurable IQR or z-score.
- Display detections with affected column(s), row numbers, explanation, risk, confidence or rule.
- Make absence of issues a real scan outcome, not a fabricated 100% perfect dataset.

### FR-03 — findings and dashboard
- Show overview cards: completeness, missing values, duplicate rows, validation/format issues.
- Define metrics mathematically (numerator/denominator, counted rows vs cells).
- List findings by issue, type, column, affected rows, severity/risk, explanation, suggested action and status.
- Allow useful filters/search/sort when implemented; no dead controls.
- Make row numbering consistent with imported CSV and show whether row 1 is header.

### FR-04 — repair planning
- Offer deterministic candidate repairs only where explainable and sensible.
- Show a before/after diff before application.
- Explain rule, expected effect and possible information loss.
- Label uncertain fixes **review needed** and allow leaving them unresolved.
- Explicitly approve or reject each proposed rule/action, ideally with scoped row selection.
- Never silently alter original input or hide discarded records.

### FR-05 — repair execution
- Apply only approved actions to the working copy.
- Preserve data types and ordering wherever possible.
- Record affected cells/rows precisely.
- Prevent duplicate application and inconsistent sequential operations.
- Rescan after every batch or on demand; update dashboard values from real results.
- Maintain changes in a reversible session history.

### FR-06 — undo/reset
- Undo an approved operation or sequence in reverse order (specify behavior in UI).
- Reset working data to its untouched upload without requiring re-upload.
- Reset audit log semantics must be clear: preserve event history even if changes are undone.
- Avoid destructive actions without an appropriate confirmation.

### FR-07 — exports
- Download cleaned CSV.
- Download findings (CSV or JSON with count, location, severity, explanation, disposition).
- Download change/audit log with timestamp, rule, actor type, target, before/after, decision, result, undo reference.
- Protect CSV exports against spreadsheet-formula injection without silently changing the internal data; document any export escaping.
- Preserve stable schema, quoting and Unicode.

### FR-08 — error states and trust
- Explain limits, parse errors, unsupported fields and ambiguous inferences.
- Mark scans, suggestions, approved repairs, completed mutations and verification as different statuses.
- Do not show fabricated statistics or success toasts.
- Never claim an AI/ML model was used if no real model is integrated.

### FR-09 — usability
- Keyboard-accessible actions, clear focus states, readable contrast, descriptive text, mobile responsive layouts.
- Handle blank state, loading state, no-findings state, error state and large-dataset summaries.
- Distinguish sample/demo records from actual user data.

## MVP vs stretch
**MVP:** one CSV, six inspection categories, recommendations with approval, undo/reset, three exports, excellent visual presentation, testable live demo.  
**Stretch:** richer schema inference, rules editor, batch review, column mapping, temporal trends, large-file chunking, comparisons. Stretch items must not jeopardize a functional MVP.

## Acceptance rule
A feature is *done* only after running the app and verifying behavior with a traceable sample case; a screenshot or mock button is insufficient.
