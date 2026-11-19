# Detection and repair policy — precise behavior

| Detector | What to check | Suggested action | Approval policy | Main risk |
|---|---|---|---|---|
| Missing values | null, empty string, whitespace-only; declared tokens | Show, optionally fill where policy specifies valid value | Always approval for fill | Inventing information |
| Exact duplicates | all selected columns equal | Mark duplicate copies, propose removing selected copies | Explicit approval | Legitimate repeated events |
| Whitespace | leading/trailing whitespace | Trim selected string cells | Review before bulk apply | Meaningful whitespace |
| Category variations | case, spacing, punctuation, near spellings | Propose canonical mapping | Explicit approval | Merging distinct classes |
| Date validation | configured date columns and explicit locale/format | Propose safe standardization where unambiguous | Explicit approval | DD/MM vs MM/DD ambiguity |
| Number validation | configured numeric fields, invalid characters/types | Parse unambiguous values using declared locale | Explicit approval | Altered units/decimals |
| Outliers | numeric values outside configurable IQR or other documented rule | Flag for inspection; no automatic deletion | Human decision | Valid rare events |

## Safe automation hierarchy
- **Detect automatically** (non-mutating).
- **Suggest automatically** (non-mutating).
- **Preview before/after** and explain scope.
- **Apply only after approval**.
- **Record immutable audit event** and **rescan**.
- **Undo** or **reset** working copy.

## Deterministic checks and explanations
- Re-running scan on the same working data and settings should yield the same findings.
- Persist rule parameters (e.g. IQR multiplier, string normalization choices) in session audit metadata.
- Distinguish exact matches from fuzzy suggestions; fuzzy semantic equivalents are never certainties.
- For duplicate detection, define whether missing values count as equal and whether ID/timestamp columns are part of comparison.
- Treat potential date/number columns as hypotheses until confirmed.
- Score metrics carefully: a missing cell is not a missing row; multiple findings can affect one cell; avoid naïvely summing counts as independent errors.

## Outlier example
For a numeric column, using a documented IQR rule:
- Q1 = 25th percentile, Q3 = 75th percentile.
- IQR = Q3 − Q1.
- Candidate outlier if value < Q1 − k×IQR or > Q3 + k×IQR (e.g. k = 1.5, configurable).
- Small/skewed groups and missing/invalid values need thoughtful treatment.
- An outlier is not proof of incorrect data.

## Human-readable finding structure
- `finding_id`, `dataset_revision`, `rule_id`, `issue_type`, `severity`.
- `columns`, `row_ids`, `sample_before`, `explanation`, `proposed_action`.
- `confidence_or_basis` (rule-based, not invented probability).
- `status`: open / proposed / approved / rejected / applied / resolved / ignored / error.

## Principle
**“Autonomous” refers to autonomous discovery and proposal, not uncontrolled destructive editing.**
