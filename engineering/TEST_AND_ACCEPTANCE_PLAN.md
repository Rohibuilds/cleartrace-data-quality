# Comprehensive test and demo plan

## Test fixture
Use the freshly authored synthetic file `samples/synthetic_quality_issues.csv`. It is **not** copied from the old chat. It includes duplicate records, blanks, whitespace, category spelling/case differences, invalid dates, nonnumeric values and a potential numeric outlier.

## Mandatory tests

### Ingestion
- Valid CSV with UTF-8 text; headers and multi-line quoting.
- Empty file, zero-row file, malformed quotation, duplicate column names.
- Non-UTF-8 input and delimiter variation.
- File exceeding configured size/row bounds rejected safely.
- No unexpected network calls or persistence.
- Original bytes/data retained unchanged in session.

### Scanning
- Every specified issue class has at least one positive and one negative case.
- Multiple issues in same row do not inflate uniquely affected-row metrics.
- No false certainty for category similarity or outliers.
- No findings case displays clear success with correct denominators.
- Repeated scan unchanged gives identical result.

### Repair approval
- Preview leaves `working_df` untouched.
- Rejected proposal does not change dataset.
- Approved trim changes exactly scoped cells; unrelated values unchanged.
- Stale approval after revision change is refused or re-evaluated.
- Duplicate deletion requires explicit confirmation.
- Invalid date, ambiguous number, outlier and category mapping cannot auto-run without consent.
- Reapplying same proposal does not corrupt data or duplicate audit entries.

### Undo/reset
- Undo restores the exact previous table state for scoped operations.
- Reset restores original without re-upload.
- Audit makes the reversal explicit; do not silently erase change history.
- Errors mid-batch do not leave half-applied changes.

### Exports
- Cleaned CSV re-imports and preserves intended values/Unicode.
- Findings export includes unresolved and resolved states with explanation.
- Audit includes UTC timestamp, decision, before/after, scope and result.
- Spreadsheet formula injection cases covered (`=`, `+`, `-`, `@`, control prefix).
- No stack trace or private local filesystem path in an exported error.

### Interface
- All controls execute real operations or are honestly disabled.
- Metrics refresh from actual working data after apply/undo/reset.
- Laptop and mobile layout checked; keyboard focus and contrast verified.
- Demo mode visibly distinguished from user data.
- Accessible error text and reduced-motion support.

## Suggested judge demo script
1. Start app, upload synthetic CSV or load clearly marked demo file.
2. Show preview and actual reported row/column counts.
3. Trigger scan, show explainable findings and metric definitions.
4. Review whitespace proposal side-by-side; explicitly approve one change.
5. Show rescan updates and audit event with original and new value.
6. Undo, show original restored; repeat one different safe approved change.
7. Download cleaned dataset, findings and change log; re-import CSV.
8. Show one ambiguous value/outlier **not** silently fixed.
9. Explain local processing, limits and any remaining untested functionality.

## Completion evidence template
For each feature record: code path, test case, manual steps, observed result, passing test output or screenshot, unresolved caveats. No claims of passing tests appear in this archive.
