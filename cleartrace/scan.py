from __future__ import annotations

import re
from typing import List, Tuple
import pandas as pd

from cleartrace.models import Finding, QualityMetrics


def is_text_column(series: pd.Series) -> bool:
    return pd.api.types.is_object_dtype(series.dtype) or pd.api.types.is_string_dtype(series.dtype)


def is_likely_date_column(column_name: str, series: pd.Series) -> bool:
    name_lower = str(column_name).casefold()
    if any(token in name_lower for token in ("date", "time", "joined", "visit", "dob", "created")):
        return True
    # Probe text values for date-like formats (YYYY-MM-DD or DD/MM/YYYY)
    sample = series.dropna().astype(str).head(10)
    date_pattern = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$|^\d{1,2}[-/]\d{1,2}[-/]\d{4}$")
    matches = sum(1 for val in sample if date_pattern.match(val.strip()))
    return matches >= max(1, len(sample) // 2)


def is_likely_numeric_column(column_name: str, series: pd.Series) -> bool:
    name_lower = str(column_name).casefold()
    if any(token in name_lower for token in ("salary", "amount", "price", "age", "cost", "total", "count", "qty", "quantity")):
        return True
    # Check if > 50% of non-null values can be coerced to numeric
    sample = series.dropna().astype(str)
    if sample.empty:
        return False
    coerced = pd.to_numeric(sample, errors="coerce")
    return coerced.notna().sum() / len(sample) >= 0.5


def scan_dataset(frame: pd.DataFrame) -> Tuple[List[Finding], QualityMetrics]:
    """Deterministically inspects dataset for quality issues and calculates quality metrics."""
    findings: List[Finding] = []
    if frame.empty:
        return findings, QualityMetrics(
            total_rows=0, total_columns=0, total_cells=0,
            completeness_pct=100.0, missing_cells=0, duplicate_rows=0,
            format_violations=0, review_count=0
        )

    total_rows = len(frame)
    total_cols = len(frame.columns)
    total_cells = total_rows * total_cols
    total_missing_cells = 0
    total_format_violations = 0

    # 1. Missing Values (NA, None, empty string, whitespace only)
    for col in frame.columns:
        s = frame[col]
        missing_mask = s.isna() | (s.astype(str).str.strip() == "")
        count = int(missing_mask.sum())
        total_missing_cells += count
        if count > 0:
            row_indices = list(frame.index[missing_mask])
            display_rows = [str(r + 1) for r in row_indices[:4]]
            findings.append(Finding(
                id=f"missing::{col}",
                rule_id="missing-values",
                kind="Missing values",
                column=str(col),
                affected_count=count,
                affected_row_indices=row_indices,
                example=f"Rows {', '.join(display_rows)}{'...' if len(row_indices) > 4 else ''}",
                explanation=f"{count} cell{'s are' if count > 1 else ' is'} blank or empty in '{col}'.",
                recommendation="Review the source or supply a domain-appropriate value. ClearTrace does not invent values.",
                risk="Medium",
                action=None,
                payload=None,
            ))

    # 2. Exact Duplicate Rows
    dup_mask = frame.duplicated(keep="first")
    dup_count = int(dup_mask.sum())
    if dup_count > 0:
        row_indices = list(frame.index[dup_mask])
        display_rows = [str(r + 1) for r in row_indices[:4]]
        findings.append(Finding(
            id="duplicates::all",
            rule_id="duplicate-rows",
            kind="Exact duplicate rows",
            column="All columns",
            affected_count=dup_count,
            affected_row_indices=row_indices,
            example=f"Rows {', '.join(display_rows)}{'...' if len(row_indices) > 4 else ''}",
            explanation=f"{dup_count} row{'s are' if dup_count > 1 else ' is an'} exact duplicate{'s' if dup_count > 1 else ''} of prior records.",
            recommendation="Retain the first instance and safely remove subsequent duplicate copies.",
            risk="High",
            action="remove_duplicates",
            payload={"duplicate_indices": row_indices},
        ))

    # 3. Outer Whitespace & 4. Category Variants
    for col in frame.columns:
        s = frame[col]
        if not is_text_column(s):
            continue

        text_s = s.dropna().astype(str)
        trim_mask = s.notna() & (text_s.str.strip() != text_s)
        trim_count = int(trim_mask.sum())
        if trim_count > 0:
            total_format_violations += trim_count
            row_indices = list(frame.index[trim_mask])
            sample_vals = [f'"{v}"' for v in text_s[trim_mask].head(3)]
            findings.append(Finding(
                id=f"whitespace::{col}",
                rule_id="trim-whitespace",
                kind="Outer whitespace",
                column=str(col),
                affected_count=trim_count,
                affected_row_indices=row_indices,
                example=", ".join(sample_vals),
                explanation=f"{trim_count} value{'s have' if trim_count > 1 else ' has'} leading or trailing whitespace.",
                recommendation="Strip outer whitespace to ensure consistent indexing and joins.",
                risk="Low",
                action="trim_whitespace",
                payload={"column": str(col)},
            ))

        # Category variants check (case / spacing variations)
        non_empty = text_s.str.strip()
        non_empty = non_empty[non_empty != ""]
        if not non_empty.empty:
            groups: dict[str, list[str]] = {}
            for val in non_empty.unique():
                groups.setdefault(val.casefold(), []).append(val)

            mapping: dict[str, str] = {}
            counts = non_empty.value_counts()
            for key, variants in groups.items():
                if len(variants) > 1:
                    # Choose canonical: highest frequency, tiebreak by original case
                    canonical = sorted(variants, key=lambda v: (-int(counts.get(v, 0)), v))[0]
                    for var in variants:
                        if var != canonical:
                            mapping[var] = canonical

            if mapping:
                variant_mask = non_empty.isin(mapping)
                affected = int(variant_mask.sum())
                if affected > 0:
                    total_format_violations += affected
                    row_indices = list(frame.index[s.isin(mapping)])
                    examples = [f'"{old}" → "{new}"' for old, new in list(mapping.items())[:3]]
                    findings.append(Finding(
                        id=f"category::{col}",
                        rule_id="category-variants",
                        kind="Category variants",
                        column=str(col),
                        affected_count=affected,
                        affected_row_indices=row_indices,
                        example="; ".join(examples),
                        explanation=f"{affected} record{'s have' if affected > 1 else ' has'} case/spacing variants for the same category.",
                        recommendation="Unify spelling to the most frequent variant observed in the dataset.",
                        risk="Medium",
                        action="normalize_categories",
                        payload={"column": str(col), "mapping": mapping},
                    ))

    # 5. Date Validation
    for col in frame.columns:
        s = frame[col]
        if is_likely_date_column(col, s):
            text_s = s.dropna().astype(str).str.strip()
            non_empty = text_s[text_s != ""]
            if not non_empty.empty:
                parsed = pd.to_datetime(non_empty, errors="coerce", format="mixed")
                invalid_mask = parsed.isna()
                invalid_count = int(invalid_mask.sum())
                if invalid_count > 0:
                    total_format_violations += invalid_count
                    row_indices = list(non_empty.index[invalid_mask])
                    bad_samples = non_empty[invalid_mask].head(3).tolist()
                    findings.append(Finding(
                        id=f"date::{col}",
                        rule_id="invalid-dates",
                        kind="Invalid date format",
                        column=str(col),
                        affected_count=invalid_count,
                        affected_row_indices=row_indices,
                        example=", ".join(bad_samples),
                        explanation=f"{invalid_count} date string{'s' if invalid_count > 1 else ''} cannot be parsed (e.g. invalid calendar dates like '2026-02-30').",
                        recommendation="Review the source records. ClearTrace flags invalid dates for human review.",
                        risk="High",
                        action=None,
                        payload=None,
                    ))

    # 6. Numeric Validation & Outlier Detection
    for col in frame.columns:
        s = frame[col]
        if is_likely_numeric_column(col, s):
            text_s = s.dropna().astype(str).str.strip()
            non_empty = text_s[text_s != ""]
            if not non_empty.empty:
                numeric_coerced = pd.to_numeric(non_empty, errors="coerce")
                non_num_mask = numeric_coerced.isna()
                non_num_count = int(non_num_mask.sum())
                if non_num_count > 0:
                    total_format_violations += non_num_count
                    row_indices = list(non_empty.index[non_num_mask])
                    bad_samples = non_empty[non_num_mask].head(3).tolist()
                    findings.append(Finding(
                        id=f"numeric::{col}",
                        rule_id="invalid-numbers",
                        kind="Invalid numeric values",
                        column=str(col),
                        affected_count=non_num_count,
                        affected_row_indices=row_indices,
                        example=", ".join(bad_samples),
                        explanation=f"{non_num_count} cell{'s contain' if non_num_count > 1 else ' contains'} non-numeric text in numeric column '{col}'.",
                        recommendation="Inspect source values; non-numeric entries require human decision.",
                        risk="Medium",
                        action=None,
                        payload=None,
                    ))

                # IQR Outlier Check on valid numbers
                valid_nums = numeric_coerced.dropna()
                if len(valid_nums) >= 4:
                    q1 = valid_nums.quantile(0.25)
                    q3 = valid_nums.quantile(0.75)
                    iqr = q3 - q1
                    if iqr > 0:
                        low_bound = q1 - 1.5 * iqr
                        high_bound = q3 + 1.5 * iqr
                        outlier_mask = (valid_nums < low_bound) | (valid_nums > high_bound)
                        outlier_count = int(outlier_mask.sum())
                        if outlier_count > 0:
                            row_indices = list(valid_nums.index[outlier_mask])
                            samples = [str(val) for val in valid_nums[outlier_mask].head(3)]
                            findings.append(Finding(
                                id=f"outlier::{col}",
                                rule_id="numeric-outliers",
                                kind="Potential numeric outlier",
                                column=str(col),
                                affected_count=outlier_count,
                                affected_row_indices=row_indices,
                                example=", ".join(samples),
                                explanation=f"{outlier_count} value{'s fall' if outlier_count > 1 else ' falls'} outside the IQR threshold ({low_bound:g} to {high_bound:g}).",
                                recommendation="Unusual values are surfaced for human inspection; an outlier is not necessarily an error.",
                                risk="Medium",
                                action=None,
                                payload=None,
                            ))

    # Calculate overall metrics
    filled_cells = total_cells - total_missing_cells
    completeness_pct = round((filled_cells / total_cells * 100.0) if total_cells > 0 else 100.0, 1)
    review_count = sum(f.affected_count for f in findings if f.risk in ("High", "Medium", "Review"))

    metrics = QualityMetrics(
        total_rows=total_rows,
        total_columns=total_cols,
        total_cells=total_cells,
        completeness_pct=completeness_pct,
        missing_cells=total_missing_cells,
        duplicate_rows=dup_count,
        format_violations=total_format_violations,
        review_count=review_count,
    )

    return findings, metrics
