from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
import streamlit as st


st.set_page_config(page_title="DataFix | Data Quality Studio", page_icon="✳", layout="wide")

st.markdown(
    """
    <style>
    .stApp { background: #f5f7fb; }
    [data-testid="stHeader"] { background: rgba(245,247,251,.85); }
    .hero { padding: 1.35rem 1.6rem; border-radius: 18px; color: white;
            background: linear-gradient(120deg,#10213c 0%,#193a63 62%,#246b78 100%);
            margin-bottom: 1rem; }
    .hero h1 { margin: 0; font-size: 2.15rem; }
    .hero p { margin: .35rem 0 0; color: #dce8f5; }
    .note { padding: .8rem 1rem; border-left: 4px solid #d6a94c;
            background: #fff8e8; border-radius: 8px; }
    </style>
    """,
    unsafe_allow_html=True,
)


def demo_data() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Record ID": "R-1001", "Name": "Asha Rao", "City": "Bengaluru", "Visit Date": "2026-10-02", "Age": 19, "Status": "Active"},
            {"Record ID": "R-1002", "Name": "Kiran Das ", "City": " bengaluru", "Visit Date": "02/10/2026", "Age": 20, "Status": "active"},
            {"Record ID": "R-1003", "Name": "Meera N", "City": "Mysuru", "Visit Date": "2026-10-04", "Age": 21, "Status": "Active"},
            {"Record ID": "R-1004", "Name": "Asha Rao", "City": "Bengaluru", "Visit Date": "2026-10-02", "Age": 19, "Status": "Active"},
            {"Record ID": "R-1005", "Name": "Ravi K", "City": "MYSURU", "Visit Date": "not-a-date", "Age": 22, "Status": "Pending"},
            {"Record ID": "R-1006", "Name": "Sara P", "City": "Mysuru ", "Visit Date": "2026-10-07", "Age": 250, "Status": "Active"},
            {"Record ID": "R-1007", "Name": "Dev M", "City": "Bengaluru", "Visit Date": "2026-10-08", "Age": None, "Status": "Pending"},
            {"Record ID": "R-1008", "Name": "Leela S", "City": "BENGALURU", "Visit Date": "2026-10-09", "Age": 18, "Status": "Active"},
        ]
    )


def sample_value(series: pd.Series, mask: pd.Series, limit: int = 4) -> str:
    values = series[mask].dropna().astype(str).head(limit).tolist()
    return ", ".join(values) if values else "—"


def scan_dataset(frame: pd.DataFrame) -> list[dict]:
    findings: list[dict] = []
    if frame.empty:
        return findings

    for column in frame.columns:
        missing = frame[column].isna()
        count = int(missing.sum())
        if count:
            findings.append({
                "id": f"missing::{column}", "kind": "Missing values", "column": str(column),
                "affected": count, "example": f"Rows {', '.join(str(i + 2) for i in frame.index[missing][:4])}",
                "recommendation": "Review the source or choose a domain-appropriate value; no value was invented.",
                "risk": "Review", "action": None, "payload": None,
            })

    dup_mask = frame.duplicated(keep="first")
    dup_count = int(dup_mask.sum())
    if dup_count:
        findings.append({
            "id": "duplicates::all", "kind": "Exact duplicate rows", "column": "All columns",
            "affected": dup_count, "example": f"Rows {', '.join(str(i + 2) for i in frame.index[dup_mask][:4])}",
            "recommendation": "Keep the first copy and remove later exact copies after review.",
            "risk": "Low", "action": "remove_duplicates", "payload": None,
        })

    for column in frame.columns:
        series = frame[column]
        if not (pd.api.types.is_object_dtype(series.dtype) or pd.api.types.is_string_dtype(series.dtype)):
            continue
        text = series.dropna().astype(str)
        trim_mask = series.notna() & series.astype("string").str.strip().ne(series.astype("string"))
        trim_count = int(trim_mask.sum())
        if trim_count:
            findings.append({
                "id": f"whitespace::{column}", "kind": "Outer whitespace", "column": str(column),
                "affected": trim_count, "example": sample_value(series, trim_mask),
                "recommendation": "Remove spaces at the start or end of text values.",
                "risk": "Low", "action": "trim_whitespace", "payload": None,
            })

        cleaned = text.str.strip()
        groups: dict[str, list[str]] = {}
        for value in cleaned.unique().tolist():
            groups.setdefault(value.casefold(), []).append(value)
        mapping: dict[str, str] = {}
        for variants in groups.values():
            if len(variants) < 2:
                continue
            counts = cleaned.value_counts()
            canonical = sorted(variants, key=lambda v: (-int(counts.get(v, 0)), v.casefold(), v))[0]
            for variant in variants:
                if variant != canonical:
                    mapping[variant] = canonical
        if mapping:
            affected = int(series.dropna().astype(str).str.strip().isin(mapping).sum())
            examples = [f"{old} → {new}" for old, new in list(mapping.items())[:3]]
            findings.append({
                "id": f"category::{column}", "kind": "Category spelling variants", "column": str(column),
                "affected": affected, "example": "; ".join(examples),
                "recommendation": "Unify case/spacing variants to the most frequent spelling in this column.",
                "risk": "Review", "action": "normalize_categories", "payload": mapping,
            })

        if any(token in str(column).casefold() for token in ("date", "time")) and len(text):
            parsed = pd.to_datetime(text, errors="coerce", format="mixed")
            invalid_count = int(parsed.isna().sum())
            if invalid_count:
                invalid_mask = series.notna() & pd.to_datetime(series, errors="coerce", format="mixed").isna()
                findings.append({
                    "id": f"date::{column}", "kind": "Unrecognized date/time", "column": str(column),
                    "affected": invalid_count, "example": sample_value(series, invalid_mask),
                    "recommendation": "Check the original source and expected date format; values were not changed.",
                    "risk": "Review", "action": None, "payload": None,
                })

        numeric = pd.to_numeric(series, errors="coerce").dropna()
        if len(numeric) >= 5:
            q1, q3 = numeric.quantile([0.25, 0.75])
            spread = q3 - q1
            if spread > 0:
                low, high = q1 - 1.5 * spread, q3 + 1.5 * spread
                outlier_mask = series.notna() & pd.to_numeric(series, errors="coerce").lt(low).fillna(False)
                outlier_mask |= series.notna() & pd.to_numeric(series, errors="coerce").gt(high).fillna(False)
                outlier_count = int(outlier_mask.sum())
                if outlier_count:
                    findings.append({
                        "id": f"outlier::{column}", "kind": "Possible numeric outliers", "column": str(column),
                        "affected": outlier_count, "example": sample_value(series, outlier_mask),
                        "recommendation": f"Review values outside the observed IQR range ({low:g} to {high:g}); unusual does not always mean wrong.",
                        "risk": "Review", "action": None, "payload": None,
                    })
    return findings


def quality_counts(frame: pd.DataFrame, findings: list[dict]) -> tuple[int, int, int]:
    missing = int(frame.isna().sum().sum())
    duplicates = int(frame.duplicated(keep="first").sum())
    review_items = sum(item["affected"] for item in findings if item["risk"] == "Review")
    return missing, duplicates, review_items


def apply_action(frame: pd.DataFrame, finding: dict) -> tuple[pd.DataFrame, int, str]:
    result = frame.copy()
    action = finding["action"]
    column = finding["column"]
    if action == "trim_whitespace":
        before = result[column].copy()
        result[column] = result[column].map(lambda value: value.strip() if isinstance(value, str) else value)
        changed = int((before.fillna("__NA__").astype(str) != result[column].fillna("__NA__").astype(str)).sum())
        return result, changed, "Removed outer spaces from text values."
    if action == "normalize_categories":
        before = result[column].copy()
        mapping = finding["payload"] or {}
        result[column] = result[column].map(
            lambda value: mapping.get(value.strip(), value.strip()) if isinstance(value, str) else value
        )
        changed = int((before.fillna("__NA__").astype(str) != result[column].fillna("__NA__").astype(str)).sum())
        return result, changed, "Unified case/spacing variants using the most frequent observed spelling."
    if action == "remove_duplicates":
        before = len(result)
        result = result.drop_duplicates(keep="first").reset_index(drop=True)
        changed = before - len(result)
        return result, changed, "Kept the first exact row and removed later exact copies."
    return result, 0, "No safe automatic action is available."


def csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8-sig")


if "source_df" not in st.session_state:
    st.session_state.source_df = None
    st.session_state.cleaned_df = None
    st.session_state.filename = None
    st.session_state.change_log = []
    st.session_state.scan_version = 0

st.markdown(
    '<div class="hero"><h1>DataFix</h1><p>Inspect, review, repair, and validate data—with a traceable record of every accepted change.</p></div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.subheader("Start with a dataset")
    uploaded = st.file_uploader("Upload a CSV file", type=["csv"], help="Files are processed by this app session. Maximum supported size: 10 MB.")
    if st.button("Load the demo dataset", use_container_width=True):
        demo = demo_data()
        st.session_state.source_df = demo.copy()
        st.session_state.cleaned_df = demo.copy()
        st.session_state.filename = "datafix_demo.csv"
        st.session_state.change_log = []
        st.session_state.scan_version += 1

if uploaded is not None and st.session_state.filename != uploaded.name:
    raw = uploaded.getvalue()
    if len(raw) > 10 * 1024 * 1024:
        st.error("This prototype supports CSV files up to 10 MB.")
    else:
        try:
            loaded = pd.read_csv(io.BytesIO(raw))
            st.session_state.source_df = loaded.copy()
            st.session_state.cleaned_df = loaded.copy()
            st.session_state.filename = uploaded.name
            st.session_state.change_log = []
            st.session_state.scan_version += 1
        except Exception as exc:
            st.error(f"Could not read this CSV: {exc}")

if st.session_state.cleaned_df is None:
    st.info("Upload a CSV or load the demo dataset to begin. The demo includes sample data-quality issues so you can try the workflow.")
    st.markdown('<div class="note"><b>Trust by design:</b> missing values and unusual numbers are flagged for review. DataFix does not invent values or silently change uncertain records.</div>', unsafe_allow_html=True)
    st.stop()

df = st.session_state.cleaned_df
findings = scan_dataset(df)
missing, duplicates, review_count = quality_counts(df, findings)

st.caption(f"Dataset: {st.session_state.filename} · {len(df):,} rows · {len(df.columns):,} columns")
metric_cols = st.columns(4)
metric_cols[0].metric("Records", f"{len(df):,}")
metric_cols[1].metric("Fields", f"{len(df.columns):,}")
metric_cols[2].metric("Missing cells", f"{missing:,}")
metric_cols[3].metric("Exact duplicate rows", f"{duplicates:,}")

tab_review, tab_data, tab_history = st.tabs(["Review findings", "Dataset preview", "Change history"])

with tab_review:
    st.subheader("Quality scan")
    if not findings:
        st.success("No issues were found by the current checks. This does not prove the dataset is error-free.")
    else:
        st.caption(f"{len(findings)} finding groups · {review_count:,} affected cells/records are marked for human review")
        display = pd.DataFrame([
            {"Finding": f["kind"], "Column": f["column"], "Affected": f["affected"],
             "Example": f["example"], "Recommendation": f["recommendation"], "Risk": f["risk"], "Issue ID": f["id"]}
            for f in findings
        ])
        st.dataframe(display.drop(columns=["Issue ID"]), hide_index=True, use_container_width=True)
        actionable = {f["id"]: f for f in findings if f["action"]}
        labels = {f'{f["kind"]} · {f["column"]} ({f["affected"]} affected)': issue_id
                  for issue_id, f in actionable.items()}
        selected_labels = st.multiselect(
            "Choose proposed actions to apply",
            options=list(labels),
            help="Only listed actions can change data. Missing values, unrecognized dates, and outliers remain review-only; category normalization is an explicit user-approved suggestion.",
        )
        selected_ids = [labels[label] for label in selected_labels]
        if selected_ids:
            st.warning("Selected changes will update the working copy. The original upload remains unchanged in this session.")
        if st.button("Apply selected safe actions", type="primary", disabled=not selected_ids):
            working = st.session_state.cleaned_df.copy()
            for issue_id in selected_ids:
                current_findings = {item["id"]: item for item in scan_dataset(working)}
                finding = current_findings.get(issue_id)
                if finding is None or finding["action"] is None:
                    continue
                working, changed, detail = apply_action(working, finding)
                st.session_state.change_log.append({
                    "Time": datetime.now().strftime("%H:%M:%S"), "Action": finding["kind"],
                    "Column": finding["column"], "Items changed": changed, "Details": detail,
                })
            st.session_state.cleaned_df = working
            st.session_state.scan_version += 1
            st.rerun()
    st.markdown('<div class="note"><b>Review-only:</b> missing values, invalid dates, and possible outliers are never auto-corrected. Their right value depends on the source and context.</div>', unsafe_allow_html=True)

with tab_data:
    left, right = st.columns([1.2, 1])
    with left:
        st.subheader("Current working copy")
        st.dataframe(df.head(100), use_container_width=True, height=360)
        st.caption("Showing up to the first 100 rows. The uploaded source remains available in this session for comparison.")
    with right:
        st.subheader("Export")
        st.download_button("Download cleaned CSV", data=csv_bytes(df), file_name="datafix_cleaned.csv", mime="text/csv", use_container_width=True)
        report_rows = [{k: v for k, v in f.items() if k not in ("payload",)} for f in findings]
        report = pd.DataFrame(report_rows)
        if report.empty:
            report = pd.DataFrame(columns=["id", "kind", "column", "affected", "example", "recommendation", "risk", "action"])
        st.download_button("Download current findings", data=report.to_csv(index=False).encode("utf-8-sig"), file_name="datafix_findings.csv", mime="text/csv", use_container_width=True)
        history = pd.DataFrame(st.session_state.change_log)
        if history.empty:
            history = pd.DataFrame(columns=["Time", "Action", "Column", "Items changed", "Details"])
        st.download_button("Download change log", data=history.to_csv(index=False).encode("utf-8-sig"), file_name="datafix_change_log.csv", mime="text/csv", use_container_width=True)
        st.caption("Exported findings describe the current working copy. Download the change log to see accepted repairs.")

with tab_history:
    st.subheader("Accepted changes")
    history = pd.DataFrame(st.session_state.change_log)
    if history.empty:
        st.info("No changes have been applied yet. Review a low-risk suggestion to record the first change.")
    else:
        st.dataframe(history, hide_index=True, use_container_width=True)
    if st.session_state.source_df is not None:
        with st.expander("Compare original upload with current working copy"):
            st.write("Original upload")
            st.dataframe(st.session_state.source_df.head(30), use_container_width=True)

st.divider()
st.caption("DataFix prototype · Rule-based checks only · Findings are indicators for review, not final judgments")
