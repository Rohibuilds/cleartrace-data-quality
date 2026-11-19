from __future__ import annotations

from typing import List, Tuple
import pandas as pd

from cleartrace.models import Finding, RepairProposal, CellDiff


def generate_proposal(finding: Finding, frame: pd.DataFrame) -> RepairProposal:
    """Generates a non-mutating preview and proposal for an actionable finding."""
    col = finding.column
    action = finding.action
    diffs: List[CellDiff] = []
    before_summary = ""
    after_summary = ""

    if action == "trim_whitespace":
        target_rows = finding.affected_row_indices
        for idx in target_rows[:5]:
            orig = str(frame.loc[idx, col])
            cleaned = orig.strip()
            diffs.append(CellDiff(row_idx=idx + 1, column=col, before=orig, after=cleaned))
        before_summary = f'Values with outer whitespace in "{col}"'
        after_summary = f'Trimmed text values in "{col}"'

    elif action == "normalize_categories":
        target_rows = finding.affected_row_indices
        mapping = (finding.payload or {}).get("mapping", {})
        for idx in target_rows[:5]:
            orig = str(frame.loc[idx, col])
            cleaned = mapping.get(orig.strip(), orig.strip())
            diffs.append(CellDiff(row_idx=idx + 1, column=col, before=orig, after=cleaned))
        before_summary = f'Spelling/case variants in "{col}"'
        after_summary = f'Unified to canonical variants in "{col}"'

    elif action in ("correct_math_mismatch", "fill_calculated") or finding.rule_id.startswith("math_"):
        target_rows = finding.affected_row_indices
        payload = finding.payload or {}
        proposed_val = payload.get("proposed_value")
        for idx in target_rows:
            orig = str(frame.loc[idx, col]) if idx in frame.index else finding.example
            diffs.append(CellDiff(row_idx=idx, column=col, before=orig, after=proposed_val))
        before_summary = f"Recorded {col}: {payload.get('observed') or 'missing'}"
        after_summary = f"Calculated {col}: {proposed_val}"

    elif action == "remove_duplicates":
        target_rows = finding.affected_row_indices
        for idx in target_rows[:5]:
            first_idx = frame[frame.duplicated(keep=False) & (frame.index == idx)].index[0]
            diffs.append(CellDiff(
                row_idx=idx + 1,
                column="All columns",
                before=f"Duplicate row (identical to row {first_idx + 1})",
                after="Row deleted",
            ))
        before_summary = f"{len(target_rows)} duplicate row{'s' if len(target_rows) > 1 else ''}"
        after_summary = "First copy preserved; duplicate copies deleted"

    else:
        target_rows = []
        before_summary = "No automated repair available."
        after_summary = "Review-only finding."

    return RepairProposal(
        proposal_id=f"prop-{finding.id}",
        finding_id=finding.id,
        rule_id=finding.rule_id,
        column=col,
        target_rows=target_rows,
        before_summary=before_summary,
        after_summary=after_summary,
        diff_sample=diffs,
        risk=finding.risk,
        explanation=finding.explanation,
        status="Proposed",
    )


def apply_repair(frame: pd.DataFrame, proposal: RepairProposal) -> Tuple[pd.DataFrame, int, str]:
    """Applies an approved repair proposal to a copy of the working DataFrame."""
    result = frame.copy()
    action = proposal.rule_id
    col = proposal.column

    if action.startswith("math_") or "math" in action or proposal.rule_id in ("correct_math_mismatch", "fill_calculated"):
        changed = 0
        for diff in proposal.diff_sample:
            if diff.row_idx in result.index and diff.column in result.columns:
                result.at[diff.row_idx, diff.column] = str(diff.after)
                changed += 1
        return result, changed, f"Applied mathematical correction: updated {changed} cell(s) in column '{col}' to calculated expected value."

    elif action == "trim-whitespace":
        before_series = result[col].copy()
        result[col] = result[col].map(lambda val: val.strip() if isinstance(val, str) else val)
        changed = int((before_series.fillna("__NA__") != result[col].fillna("__NA__")).sum())
        return result, changed, f"Trimmed outer whitespace across {changed} cell(s) in column '{col}'."

    elif action == "category-variants":
        # We need the mapping from the finding or proposal
        # Re-derive or map variants
        s = result[col].dropna().astype(str).str.strip()
        groups: dict[str, list[str]] = {}
        for val in s.unique():
            groups.setdefault(val.casefold(), []).append(val)
        mapping: dict[str, str] = {}
        counts = s.value_counts()
        for key, variants in groups.items():
            if len(variants) > 1:
                canonical = sorted(variants, key=lambda v: (-int(counts.get(v, 0)), v))[0]
                for var in variants:
                    if var != canonical:
                        mapping[var] = canonical

        before_series = result[col].copy()
        result[col] = result[col].map(
            lambda val: mapping.get(val.strip(), val.strip()) if isinstance(val, str) else val
        )
        changed = int((before_series.fillna("__NA__") != result[col].fillna("__NA__")).sum())
        return result, changed, f"Normalized {changed} category value(s) in column '{col}' to canonical spellings."

    elif action == "duplicate-rows":
        before_count = len(result)
        result = result.drop_duplicates(keep="first").reset_index(drop=True)
        changed = before_count - len(result)
        return result, changed, f"Removed {changed} duplicate row(s), keeping the first instance."

    return result, 0, "No action applied."

