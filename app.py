from decimal import Decimal
import io
from typing import Optional, List, Dict, Any
import pandas as pd
import streamlit as st

from cleartrace.ingest import (
    parse_document_bytes,
    load_demo_dataset,
    load_math_demo_dataset,
    IngestionError,
)
from cleartrace.scan import scan_dataset
from cleartrace.repair import generate_proposal
from cleartrace.audit import SessionManager, StaleRevisionError
from cleartrace.scoring import calculate_quality_score
from cleartrace.passport import generate_data_passport, simulate_impact
from cleartrace.export import export_cleaned_csv, export_findings_report, export_audit_log
from cleartrace.math_engine import inspect_invoice_dataset, convert_math_findings_to_proposals
from cleartrace.retrieval import build_session_evidence_index
from cleartrace.llm_assistant import get_llm_status, ask_knowledge_assistant

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIGURATION & ENTERPRISE DESIGN TOKENS
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="ClearTrace | Enterprise Data Quality Studio",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
      --ct-canvas: #F6F8FB;
      --ct-navy-950: #091322;
      --ct-navy-900: #0F1D35;
      --ct-navy-700: #1E3A5F;
      --ct-navy-500: #3A5880;
      --ct-navy-100: #E4EAF2;
      --ct-surface-card: #FFFFFF;
      --ct-surface-alt: #F8FAFC;
      --ct-teal-600: #1B7A6E;
      --ct-teal-500: #24A99A;
      --ct-teal-100: #D8F3F0;
      --ct-gold-500: #C89A2E;
      --ct-gold-100: #FBF3DC;
      --ct-risk-high-bg: #FEEAEA;
      --ct-risk-high-txt: #991B1B;
      --ct-risk-med-bg: #FEF3C7;
      --ct-risk-med-txt: #92400E;
      --ct-risk-low-bg: #E6F7F3;
      --ct-risk-low-txt: #115E59;
    }

    [data-testid="stAppViewContainer"] {
      background-color: #F6F8FB;
      background-image:
        radial-gradient(ellipse 65% 50% at 92% 5%, rgba(36, 169, 154, 0.08) 0%, transparent 60%),
        radial-gradient(ellipse 45% 40% at 8% 95%, rgba(200, 154, 46, 0.05) 0%, transparent 55%),
        url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='28' height='28'%3E%3Ccircle cx='1' cy='1' r='0.8' fill='%231E3A5F' fill-opacity='0.05'/%3E%3C/svg%3E");
      background-size: 100% 100%, 100% 100%, 28px 28px;
      background-repeat: no-repeat, no-repeat, repeat;
    }

    [data-testid="stHeader"] {
      background: rgba(246, 248, 251, 0.85) !important;
      backdrop-filter: blur(12px);
    }

    .ct-card {
      background: #FFFFFF;
      border: 1px solid #E4EAF2;
      border-radius: 12px;
      padding: 20px 24px;
      box-shadow: 0 1px 3px rgba(15,29,53,0.05), 0 6px 16px rgba(15,29,53,0.04);
      margin-bottom: 16px;
    }

    .ct-score-box {
      background: linear-gradient(135deg, #FFFFFF 0%, #F8FAFC 100%);
      border: 1px solid #E4EAF2;
      border-radius: 14px;
      padding: 24px 28px;
      display: flex;
      align-items: center;
      gap: 28px;
      margin-bottom: 20px;
    }

    .ct-score-ring {
      width: 90px;
      height: 90px;
      border-radius: 50%;
      border: 5px solid #24A99A;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      background: #FFFFFF;
    }

    .ct-badge {
      display: inline-block;
      padding: 2px 9px;
      border-radius: 999px;
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.03em;
    }
    .ct-badge-high { background: #FEEAEA; color: #991B1B; }
    .ct-badge-med { background: #FEF3C7; color: #92400E; }
    .ct-badge-low { background: #E6F7F3; color: #115E59; }

    .ct-diff-del { color: #991B1B; background: #FEEAEA; padding: 2px 6px; border-radius: 4px; text-decoration: line-through; }
    .ct-diff-add { color: #115E59; background: #E6F7F3; padding: 2px 6px; border-radius: 4px; font-weight: 700; }

    .ct-trust-note {
      background: #FBF3DC;
      border-left: 4px solid #C89A2E;
      border-radius: 6px;
      padding: 14px 18px;
      font-size: 0.84rem;
      color: #1E3A5F;
      margin: 16px 0 20px;
      line-height: 1.5;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE INITIALIZATION
# ─────────────────────────────────────────────────────────────────────────────

if "session_manager" not in st.session_state:
    st.session_state.session_manager: Optional[SessionManager] = None
    st.session_state.selected_nav = "Command Center"

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(
        """
        <div style="display:flex;align-items:center;gap:12px;padding:6px 0 16px 0;border-bottom:1px solid rgba(0,0,0,0.08);">
          <div style="width:36px;height:36px;border-radius:9px;background:linear-gradient(135deg,#24A99A 0%,#15294A 100%);display:flex;align-items:center;justify-content:center;color:white;font-weight:800;font-size:16px;">
            CT
          </div>
          <div>
            <div style="font-weight:700;font-size:1.15rem;color:#0F1D35;line-height:1.2;">ClearTrace</div>
            <div style="font-size:0.62rem;color:#1B7A6E;letter-spacing:0.08em;text-transform:uppercase;font-weight:600;">Data Intelligence</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div style="display:inline-flex;align-items:center;gap:6px;background:#FBF3DC;border:1px solid rgba(200,154,46,0.3);border-radius:999px;padding:4px 11px;margin:12px 0;font-size:0.7rem;font-weight:700;color:#8F6D1D;">
          🔒 Session Only · Local In-Memory
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("Data Ingestion")
    uploaded_file = st.file_uploader(
        "Upload Dataset",
        type=["csv", "xlsx", "pdf"],
        help="Local in-memory processing. Max size: 10 MB, 100k rows, 15 PDF pages.",
    )

    if uploaded_file is not None:
        current_sm = st.session_state.session_manager
        if current_sm is None or current_sm.filename != uploaded_file.name:
            try:
                raw_bytes = uploaded_file.getvalue()
                df_loaded, meta = parse_document_bytes(raw_bytes, filename=uploaded_file.name)
                st.session_state.session_manager = SessionManager(
                    df_loaded,
                    filename=uploaded_file.name,
                    provenance_map=meta.get("provenance_map"),
                    document_format=meta.get("format", "csv"),
                    warnings=meta.get("warnings"),
                )
                st.rerun()
            except IngestionError as err:
                st.error(f"Upload error: {err}")

    st.caption("Demonstration Datasets")
    if st.button("📊 Quality Issues Demo (CSV)", use_container_width=True):
        demo_df = load_demo_dataset()
        st.session_state.session_manager = SessionManager(demo_df, filename="synthetic_quality_issues.csv")
        st.rerun()

    c_m1, c_m2 = st.columns(2)
    with c_m1:
        if st.button("🔢 Math (CSV)", use_container_width=True, help="Load synthetic invoice CSV with arithmetic errors"):
            df, meta = load_math_demo_dataset("csv")
            st.session_state.session_manager = SessionManager(
                df,
                filename=meta["filename"],
                provenance_map=meta.get("provenance_map"),
                document_format=meta.get("format", "csv"),
            )
            st.rerun()
    with c_m2:
        if st.button("📑 Math (XLSX)", use_container_width=True, help="Load synthetic invoice Excel XLSX with formulas"):
            df, meta = load_math_demo_dataset("xlsx")
            st.session_state.session_manager = SessionManager(
                df,
                filename=meta["filename"],
                provenance_map=meta.get("provenance_map"),
                document_format=meta.get("format", "xlsx"),
                warnings=meta.get("warnings"),
            )
            st.rerun()

    if st.button("📄 Math Invoice (PDF)", use_container_width=True, help="Load synthetic invoice PDF text extraction"):
        df, meta = load_math_demo_dataset("pdf")
        st.session_state.session_manager = SessionManager(
            df,
            filename=meta["filename"],
            provenance_map=meta.get("provenance_map"),
            document_format=meta.get("format", "pdf"),
            warnings=meta.get("warnings"),
        )
        st.rerun()

    st.divider()

    nav_choice = st.radio(
        "Platform Modules",
        options=[
            "Command Center",
            "Dataset Workspace",
            "Mathematical Intelligence",
            "Data Observatory",
            "Repair Studio",
            "AI Knowledge Assistant (RAG)",
            "Data Passport",
            "Audit Ledger & Time Machine",
            "Trust Vault",
        ],
        label_visibility="collapsed",
    )
    st.session_state.selected_nav = nav_choice

    st.caption("ClearTrace Enterprise Studio v2.0 · Local-First")

# ─────────────────────────────────────────────────────────────────────────────
# MAIN DASHBOARD CONTENT
# ─────────────────────────────────────────────────────────────────────────────

sm = st.session_state.session_manager

if sm is None:
    st.markdown(
        """
        <div style="background:#FFFFFF;border:1px solid #E4EAF2;border-radius:14px;padding:36px;margin:24px 0;box-shadow:0 2px 8px rgba(15,29,53,0.06);">
          <h2 style="color:#0F1D35;font-weight:800;margin-bottom:8px;">Understand every anomaly. Control every correction.</h2>
          <p style="color:#3A5880;font-size:1.02rem;max-width:700px;line-height:1.6;">
            ClearTrace scans your CSV for quality issues, clearly explains what was found and why it matters,
            and lets you review side-by-side previews before approving any safe repair.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns([1, 1])
    with c1:
        st.info("👈 Upload your CSV in the sidebar or click **'Load Synthetic Demonstration CSV'** to begin.")
    with c2:
        st.markdown(
            """
            <div class="ct-trust-note">
              <b>Trust before autonomy:</b> ClearTrace does not silently alter data or invent replacement values.
              Missing values and outliers are highlighted for human decision.
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# LIVE ENGINE STATE
# ─────────────────────────────────────────────────────────────────────────────

working_df = sm.working_df
findings, metrics = scan_dataset(working_df)
score_report = calculate_quality_score(working_df, findings)

# Top Bar Summary
fmt_badge_color = "#1B7A6E" if sm.document_format == "csv" else ("#1E3A5F" if sm.document_format == "xlsx" else "#8F6D1D")
fmt_badge_bg = "#D8F3F0" if sm.document_format == "csv" else ("#E4EAF2" if sm.document_format == "xlsx" else "#FBF3DC")

t1, t2 = st.columns([3, 1])
with t1:
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px;flex-wrap:wrap;">
          <div style="font-size:1.3rem;font-weight:800;color:#0F1D35;">{sm.filename}</div>
          <span class="ct-badge" style="background:{fmt_badge_bg};color:{fmt_badge_color};text-transform:uppercase;">{sm.document_format}</span>
          <span class="ct-badge" style="background:#D8F3F0;color:#1B7A6E;">Revision {sm.dataset_revision}</span>
          <span style="font-size:0.82rem;color:#3A5880;">{metrics.total_rows:,} rows · {metrics.total_columns} columns · {len(sm.provenance_map)} indexed sources</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
with t2:
    if st.button("↺ Reset to Raw Baseline", help="Revert all changes and restore raw original upload", use_container_width=True):
        sm.reset_to_original()
        st.toast("Reset to raw upload baseline.", icon="↺")
        st.rerun()

if sm.warnings:
    for warn in sm.warnings:
        st.warning(f"⚠️ {warn}")

# ─────────────────────────────────────────────────────────────────────────────
# MODULE 1: COMMAND CENTER
# ─────────────────────────────────────────────────────────────────────────────

if st.session_state.selected_nav == "Command Center":
    st.markdown(
        f"""
        <div class="ct-score-box">
          <div class="ct-score-ring">
            <div style="font-size:1.8rem;font-weight:800;color:#0F1D35;line-height:1;">{score_report.overall_score:.1f}</div>
            <div style="font-size:0.68rem;font-weight:800;color:#1B7A6E;margin-top:2px;">GRADE {score_report.grade}</div>
          </div>
          <div style="flex:1;">
            <h3 style="color:#0F1D35;font-weight:700;margin-bottom:4px;">Transparent Data Hygiene Score</h3>
            <p style="color:#3A5880;font-size:0.86rem;line-height:1.5;">{score_report.summary}</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(
            f"""
            <div class="ct-card">
              <div style="font-size:0.72rem;font-weight:700;text-transform:uppercase;color:#3A5880;">Completeness</div>
              <div style="font-size:2.1rem;font-weight:800;color:#1B7A6E;margin:6px 0;">{metrics.completeness_pct:.1f}%</div>
              <div style="font-size:0.76rem;color:#3A5880;">Non-null cells across all {metrics.total_cells:,} cells.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with k2:
        st.markdown(
            f"""
            <div class="ct-card">
              <div style="font-size:0.72rem;font-weight:700;text-transform:uppercase;color:#3A5880;">Missing Values</div>
              <div style="font-size:2.1rem;font-weight:800;color:{'#AB8224' if metrics.missing_cells else '#0F1D35'};margin:6px 0;">{metrics.missing_cells:,}</div>
              <div style="font-size:0.76rem;color:#3A5880;">Blank or empty string cells flagged for review.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with k3:
        st.markdown(
            f"""
            <div class="ct-card">
              <div style="font-size:0.72rem;font-weight:700;text-transform:uppercase;color:#3A5880;">Duplicate Rows</div>
              <div style="font-size:2.1rem;font-weight:800;color:{'#991B1B' if metrics.duplicate_rows else '#0F1D35'};margin:6px 0;">{metrics.duplicate_rows:,}</div>
              <div style="font-size:0.76rem;color:#3A5880;">Exact duplicate records across all columns.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with k4:
        st.markdown(
            f"""
            <div class="ct-card">
              <div style="font-size:0.72rem;font-weight:700;text-transform:uppercase;color:#3A5880;">Format Checks</div>
              <div style="font-size:2.1rem;font-weight:800;color:{'#AB8224' if metrics.format_violations else '#0F1D35'};margin:6px 0;">{metrics.format_violations:,}</div>
              <div style="font-size:0.76rem;color:#3A5880;">Outer whitespace, category variants, dates/numbers.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        """
        <div class="ct-trust-note">
          <b>Trust Note:</b> Unusual values, category variations, and numeric outliers are surfaced for human review.
          An anomaly is not automatic proof of bad data. ClearTrace guarantees that no changes happen without your explicit approval.
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.subheader("Summary Table of Identified Issues")
    if not findings:
        st.success("No issues detected in current working copy.")
    else:
        summary_rows = [
            {"Issue Category": f.kind, "Column": f.column, "Affected Records": f.affected_count, "Risk Level": f.risk, "Proposed Action": f.action or "Review Only"}
            for f in findings
        ]
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────────────────────
# MODULE 2: DATASET WORKSPACE
# ─────────────────────────────────────────────────────────────────────────────

elif st.session_state.selected_nav == "Dataset Workspace":
    st.subheader("Dataset Workspace & Working Preview")
    show_provenance = st.checkbox("Show Source Provenance Mapping", value=False)
    
    if show_provenance:
        display_df = sm.working_df.copy()
        display_df.insert(0, "Source Provenance", [sm.provenance_map.get(i, f"{sm.filename}:row {i+2}") for i in range(len(display_df))])
        st.dataframe(display_df, use_container_width=True, height=420)
    else:
        st.dataframe(sm.working_df, use_container_width=True, height=420)

    with st.expander("Compare with untouched raw baseline upload"):
        st.dataframe(sm.original_df, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# MODULE 3: MATHEMATICAL INTELLIGENCE
# ─────────────────────────────────────────────────────────────────────────────

elif st.session_state.selected_nav == "Mathematical Intelligence":
    st.subheader("Mathematical Error Intelligence & Arithmetic Invariants")

    st.markdown(
        """
        <div class="ct-card" style="border-left: 4px solid #1B7A6E;">
          <div style="font-weight:700;font-size:1.05rem;color:#0F1D35;margin-bottom:6px;">
            Deterministic Verification Policy · Decimal Invariant Engine
          </div>
          <div style="font-size:0.88rem;color:#1E3A5F;margin-bottom:8px;">
            <b>Grounded Formula:</b> <code>Expected Total = (Quantity × Unit Price) − Discount + Tax</code>
          </div>
          <p style="font-size:0.82rem;color:#3A5880;line-height:1.5;margin-bottom:0;">
            All calculations execute in exact <code>Decimal</code> precision with <code>ROUND_HALF_UP</code> semantics.
            ClearTrace guarantees that no LLM is used as an authoritative calculator. Discrepancies exceeding the tolerance threshold
            are surfaced with step-by-step arithmetic proofs for human approval.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c_tol, c_info = st.columns([1, 2])
    with c_tol:
        tolerance_val = st.slider(
            "Arithmetic Tolerance ($)",
            min_value=0.00,
            max_value=1.00,
            value=0.01,
            step=0.01,
            help="Tolerable rounding difference before flagging an arithmetic discrepancy.",
        )
    with c_info:
        st.markdown(
            f"""
            <div style="padding-top:14px;font-size:0.8rem;color:#3A5880;">
              Active Tolerance: <b>±${tolerance_val:.2f}</b> · Zero-LLM Arithmetic Guarantee · Reversible Cell Corrections
            </div>
            """,
            unsafe_allow_html=True,
        )

    math_findings = sm.get_math_findings(tolerance_val=tolerance_val)

    # Discrepancy KPI Cards
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.markdown(
            f"""
            <div class="ct-card" style="padding:14px;">
              <div style="font-size:0.7rem;font-weight:700;text-transform:uppercase;color:#3A5880;">Total Math Issues</div>
              <div style="font-size:1.8rem;font-weight:800;color:{'#991B1B' if math_findings else '#1B7A6E'};margin:4px 0;">{len(math_findings)}</div>
              <div style="font-size:0.72rem;color:#3A5880;">Findings flagged</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m2:
        mismatches = [f for f in math_findings if f.rule_id == "MATH_MISMATCH"]
        st.markdown(
            f"""
            <div class="ct-card" style="padding:14px;">
              <div style="font-size:0.7rem;font-weight:700;text-transform:uppercase;color:#3A5880;">Mismatched Totals</div>
              <div style="font-size:1.8rem;font-weight:800;color:{'#991B1B' if mismatches else '#0F1D35'};margin:4px 0;">{len(mismatches)}</div>
              <div style="font-size:0.72rem;color:#3A5880;">Arithmetic errors</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m3:
        missing_totals = [f for f in math_findings if f.rule_id == "MISSING_TOTAL"]
        st.markdown(
            f"""
            <div class="ct-card" style="padding:14px;">
              <div style="font-size:0.7rem;font-weight:700;text-transform:uppercase;color:#3A5880;">Missing Totals</div>
              <div style="font-size:1.8rem;font-weight:800;color:{'#AB8224' if missing_totals else '#0F1D35'};margin:4px 0;">{len(missing_totals)}</div>
              <div style="font-size:0.72rem;color:#3A5880;">Derivable totals</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m4:
        negatives = [f for f in math_findings if f.rule_id == "NEGATIVE_NOT_ALLOWED"]
        st.markdown(
            f"""
            <div class="ct-card" style="padding:14px;">
              <div style="font-size:0.7rem;font-weight:700;text-transform:uppercase;color:#3A5880;">Negative Violations</div>
              <div style="font-size:1.8rem;font-weight:800;color:{'#991B1B' if negatives else '#0F1D35'};margin:4px 0;">{len(negatives)}</div>
              <div style="font-size:0.72rem;color:#3A5880;">Quantity &lt; 0</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m5:
        invalid_nums = [f for f in math_findings if f.rule_id in ("INVALID_NUMBER", "DISCOUNT_EXCEEDS_SUBTOTAL")]
        st.markdown(
            f"""
            <div class="ct-card" style="padding:14px;">
              <div style="font-size:0.7rem;font-weight:700;text-transform:uppercase;color:#3A5880;">Syntax / Constraint</div>
              <div style="font-size:1.8rem;font-weight:800;color:{'#991B1B' if invalid_nums else '#0F1D35'};margin:4px 0;">{len(invalid_nums)}</div>
              <div style="font-size:0.72rem;color:#3A5880;">Invalid text or limits</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if not math_findings:
        st.success("✓ All records satisfy mathematical invariants and business constraints at the current tolerance threshold.")
    else:
        st.subheader("Deterministic Discrepancy Findings")
        for idx_mf, mf in enumerate(math_findings):
            badge_class = "ct-badge-high" if mf.severity == "High" else "ct-badge-med"
            with st.container():
                st.markdown(
                    f"""
                    <div class="ct-card">
                      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                        <span style="font-weight:800;font-size:1.05rem;color:#0F1D35;">
                          Invoice <code>{mf.invoice_id}</code> · {mf.rule_id}
                        </span>
                        <div>
                          <span class="ct-badge {badge_class}">{mf.severity} Severity</span>
                        </div>
                      </div>
                      <div style="font-size:0.8rem;color:#3A5880;margin-bottom:8px;">
                        📍 <b>Source Provenance:</b> <code>{mf.source_ref}</code>
                      </div>
                      <div style="display:grid;grid-template-columns: repeat(3, 1fr);gap:12px;background:#F8FAFC;padding:12px;border-radius:8px;margin-bottom:10px;font-size:0.84rem;">
                        <div><span style="color:#3A5880;">Observed / Recorded:</span><br><b>{mf.observed or 'MISSING'}</b></div>
                        <div><span style="color:#3A5880;">Expected Calculated:</span><br><b>{mf.expected or 'N/A'}</b></div>
                        <div><span style="color:#3A5880;">Arithmetic Deviation:</span><br><b style="color:{'#991B1B' if mf.deviation else '#3A5880'};">{mf.deviation or 'N/A'}</b></div>
                      </div>
                      <div style="font-size:0.8rem;background:#F6F8FB;padding:8px 12px;border-left:3px solid #1B7A6E;border-radius:4px;margin-bottom:10px;font-family:monospace;">
                        <b>Calculation:</b> {mf.calculation_steps}
                      </div>
                      <div style="font-size:0.82rem;color:#1E3A5F;margin-bottom:10px;">
                        {mf.message}
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if mf.proposed_value and mf.action:
                    c_fix, c_space = st.columns([1, 3])
                    with c_fix:
                        if st.button(f"✓ Apply Repair ({mf.invoice_id})", key=f"btn_math_fix_{mf.id}_{idx_mf}", type="primary"):
                            pairs = convert_math_findings_to_proposals([mf], sm.working_df)
                            if pairs:
                                _, prop = pairs[0]
                                try:
                                    sm.apply_proposal(prop, expected_revision=sm.dataset_revision)
                                    st.toast(f"Applied mathematical repair for {mf.invoice_id}: {mf.proposed_value}", icon="✅")
                                    st.rerun()
                                except StaleRevisionError as err:
                                    st.error(f"Cannot apply: {err}")

# ─────────────────────────────────────────────────────────────────────────────
# MODULE 4: DATA OBSERVATORY
# ─────────────────────────────────────────────────────────────────────────────

elif st.session_state.selected_nav == "Data Observatory":
    st.subheader("Data Observatory — Detailed Inspection Findings")
    for f in findings:
        badge_style = "ct-badge-high" if f.risk == "High" else ("ct-badge-med" if f.risk in ("Medium", "Review") else "ct-badge-low")
        with st.expander(f"[{f.kind}] Column: '{f.column}' · {f.affected_count} affected records", expanded=True):
            st.markdown(f"**Explanation:** {f.explanation}")
            st.markdown(f"**Recommendation:** {f.recommendation}")
            st.markdown(f"**Sample Locations:** `{f.example}`")
            st.markdown(f"Risk: <span class='ct-badge {badge_style}'>{f.risk}</span>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# MODULE 5: REPAIR STUDIO
# ─────────────────────────────────────────────────────────────────────────────

elif st.session_state.selected_nav == "Repair Studio":
    st.subheader("Repair Studio & Pre-Mutation Impact Simulator")

    # 1. Actionable Data Quality Scan Proposals
    actionable_scan = [f for f in findings if f.action is not None]

    # 2. Mathematical Proposals
    math_findings = sm.get_math_findings()
    math_pairs = convert_math_findings_to_proposals(math_findings, working_df)

    total_proposals = len(actionable_scan) + len(math_pairs)

    if total_proposals == 0:
        st.info("No actionable repair proposals pending approval.")
    else:
        st.write(f"There are **{total_proposals} actionable proposal(s)** ready for explicit human review:")

        # Render Math Proposals First (High Priority)
        if math_pairs:
            st.markdown("#### 🔢 Mathematical Recalculation Proposals")
            for m_finding, m_prop in math_pairs:
                with st.container():
                    st.markdown(
                        f"""
                        <div class="ct-card" style="border-left: 4px solid #1B7A6E;">
                          <div style="display:flex;justify-content:space-between;align-items:center;">
                            <span style="font-weight:700;font-size:1.05rem;color:#0F1D35;">
                              {m_finding.kind} · Column '{m_prop.column}' (Invoice {m_finding.invoice_id})
                            </span>
                            <span class="ct-badge ct-badge-high">{m_prop.risk} Priority</span>
                          </div>
                          <div style="font-size:0.8rem;background:#F8FAFC;padding:8px 12px;border-left:3px solid #24A99A;border-radius:4px;margin:8px 0;">
                            <b>Deterministic Calculation:</b> {m_finding.calculation_steps}
                          </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    if m_prop.diff_sample:
                        diff_rows = [
                            {"Row": d.row_idx, "Column": d.column, "Original (Before)": str(d.before), "Proposed (After)": str(d.after)}
                            for d in m_prop.diff_sample
                        ]
                        st.dataframe(pd.DataFrame(diff_rows), hide_index=True, use_container_width=True)

                    col_a, col_r = st.columns([1, 4])
                    with col_a:
                        if st.button(f"✓ Approve {m_finding.invoice_id} Recalculation", key=f"st_app_math_{m_prop.proposal_id}", type="primary"):
                            try:
                                sm.apply_proposal(m_prop, expected_revision=sm.dataset_revision)
                                st.toast(f"Approved and applied repair for {m_finding.invoice_id}", icon="✅")
                                st.rerun()
                            except StaleRevisionError as err:
                                st.error(f"Cannot apply: {err}")
                    with col_r:
                        if st.button("✕ Reject", key=f"st_rej_math_{m_prop.proposal_id}"):
                            st.info("Repair rejected. Working dataset unchanged.")

        # Render Standard Scan Proposals
        if actionable_scan:
            st.markdown("#### 🛡️ Data Quality Cleaning Proposals")
            for f in actionable_scan:
                prop = generate_proposal(f, working_df)
                sim = simulate_impact(working_df, f)

                with st.container():
                    st.markdown(
                        f"""
                        <div class="ct-card">
                          <div style="display:flex;justify-content:space-between;align-items:center;">
                            <span style="font-weight:700;font-size:1.05rem;color:#0F1D35;">{f.kind} · Column '{f.column}'</span>
                            <span class="ct-badge {'ct-badge-high' if prop.risk=='High' else 'ct-badge-low'}">{prop.risk} Risk</span>
                          </div>
                          <div style="font-size:0.8rem;background:#F8FAFC;padding:8px 12px;border-left:3px solid #24A99A;border-radius:4px;margin:8px 0;">
                            <b>Impact Simulation:</b> {sim.resolved_issue_description} · Data Loss Risk: <b>{sim.data_loss_risk}</b>
                          </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                    if prop.diff_sample:
                        diff_rows = [
                            {"Row": d.row_idx, "Column": d.column, "Original (Before)": str(d.before), "Proposed (After)": str(d.after)}
                            for d in prop.diff_sample
                        ]
                        st.dataframe(pd.DataFrame(diff_rows), hide_index=True, use_container_width=True)

                    col_a, col_r = st.columns([1, 4])
                    with col_a:
                        if st.button(f"✓ Approve {f.kind}", key=f"st_app_{f.id}", type="primary"):
                            try:
                                sm.apply_proposal(prop, expected_revision=sm.dataset_revision)
                                st.toast(f"Approved and applied repair for {f.kind}", icon="✅")
                                st.rerun()
                            except StaleRevisionError as err:
                                st.error(f"Cannot apply: {err}")
                    with col_r:
                        if st.button("✕ Reject", key=f"st_rej_{f.id}"):
                            st.info("Repair rejected. Working dataset unchanged.")

# ─────────────────────────────────────────────────────────────────────────────
# MODULE 6: AI KNOWLEDGE ASSISTANT (RAG)
# ─────────────────────────────────────────────────────────────────────────────

elif st.session_state.selected_nav == "AI Knowledge Assistant (RAG)":
    st.subheader("AI Knowledge Assistant & Session-Isolated RAG")

    llm_info = get_llm_status()
    idx = sm.get_evidence_index(quality_findings=findings)

    # Status Pill Box
    if llm_info.get("available"):
        status_color = "#1B7A6E"
        status_bg = "#D8F3F0"
        status_label = f"🟢 Local Ollama Active ({llm_info.get('model')})"
    else:
        status_color = "#8F6D1D"
        status_bg = "#FBF3DC"
        status_label = "🟡 Honest Offline Mode · Grounded Lexical Retrieval Active (Zero Hallucination)"

    st.markdown(
        f"""
        <div class="ct-card">
          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
            <div>
              <span class="ct-badge" style="background:{status_bg};color:{status_color};">{status_label}</span>
              <span style="font-size:0.8rem;color:#3A5880;margin-left:8px;">
                Indexed Passages: <b>{len(idx.passages)}</b> (Schema, Rules, Dataset Rows, and Findings)
              </span>
            </div>
            <div style="font-size:0.75rem;color:#3A5880;">
              Local loopback only: <code>http://127.0.0.1:11434</code>
            </div>
          </div>
          <p style="font-size:0.82rem;color:#3A5880;line-height:1.5;margin-top:10px;margin-bottom:0;">
            ClearTrace uses BM25 lexical ranking to retrieve verifiable source evidence before generating answers.
            Every claim is accompanied by explicit <code>[Source: ...]</code> citations mapped to the exact input document row or page.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if "rag_query" not in st.session_state:
        st.session_state.rag_query = "How is the invoice expected total calculated?"

    st.caption("Suggested Questions:")
    q_c1, q_c2, q_c3 = st.columns(3)
    with q_c1:
        if st.button("📐 Calculation Formula & Rules", use_container_width=True):
            st.session_state.rag_query = "How is the invoice expected total calculated?"
    with q_c2:
        if st.button("🔢 Discrepant Invoices", use_container_width=True):
            st.session_state.rag_query = "Which invoices have arithmetic discrepancies?"
    with q_c3:
        if st.button("📍 Provenance of INV-002", use_container_width=True):
            st.session_state.rag_query = "What is the source provenance of INV-002?"

    user_query = st.text_input(
        "Ask ClearTrace about dataset rules, anomalies, provenance, or invariants:",
        value=st.session_state.rag_query,
    )

    if user_query:
        evidence = idx.search(user_query, limit=5)
        grounded_answer = ask_knowledge_assistant(user_query, evidence)

        st.markdown(
            f"""
            <div class="ct-card" style="border-left: 4px solid #1B7A6E;margin-top:16px;">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                <span style="font-weight:700;font-size:1.05rem;color:#0F1D35;">Grounded Assistant Response</span>
                <span class="ct-badge {'ct-badge-low' if grounded_answer.status == 'llm_grounded_answer' else 'ct-badge-med'}">
                  {grounded_answer.status}
                </span>
              </div>
              <div style="font-size:0.9rem;color:#0F1D35;line-height:1.6;white-space:pre-wrap;">
{grounded_answer.answer}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.subheader("Verifiable Source Citations & Evidence Passages")
        for i, ev in enumerate(evidence):
            with st.expander(f"Citation [{i+1}] {ev.source_ref} — {ev.title} (Score: {ev.score:.3f})", expanded=(i == 0)):
                st.markdown(f"**Kind:** `{ev.kind}`")
                st.markdown(f"**Source Reference:** `{ev.source_ref}`")
                st.markdown(f"**Evidence Excerpt:**\n\n```text\n{ev.text}\n```")


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 7: DATA PASSPORT
# ─────────────────────────────────────────────────────────────────────────────

elif st.session_state.selected_nav == "Data Passport":
    st.subheader("Data Passport — Cryptographic Hygiene Certificate")
    passport = generate_data_passport(sm.original_df, sm.working_df, sm.filename, score_report, findings, sm.audit_events)

    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#FFFFFF 0%,#F8FAFC 100%);border:2px solid #44BEB0;border-radius:14px;padding:24px;box-shadow:0 4px 16px rgba(15,29,53,0.06);">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;">
            <div>
              <div style="font-size:0.75rem;letter-spacing:0.1em;text-transform:uppercase;color:#1B7A6E;font-weight:700;">ClearTrace Data Passport</div>
              <div style="font-size:1.4rem;font-weight:800;color:#0F1D35;margin:4px 0;">{passport.passport_id}</div>
              <div style="font-size:0.78rem;color:#3A5880;">Issued UTC: {passport.issued_at_utc} | Target File: <b>{passport.filename}</b></div>
            </div>
            <div style="text-align:right;">
              <div style="font-size:2rem;font-weight:800;color:#1B7A6E;line-height:1;">{passport.quality_score} <span style="font-size:1rem;color:#3A5880;">/ 100</span></div>
              <div style="font-size:0.75rem;font-weight:700;color:#1E3A5F;">Grade {passport.grade} Certified</div>
            </div>
          </div>
          <hr style="border:0;border-top:1px solid #E4EAF2;margin:16px 0;">
          <div style="font-size:0.74rem;color:#3A5880;">Original Raw CSV SHA-256 Digest:</div>
          <code style="font-size:0.74rem;">{passport.original_sha256}</code>
          <div style="font-size:0.74rem;color:#3A5880;margin-top:8px;">Cleaned Working CSV SHA-256 Digest:</div>
          <code style="font-size:0.74rem;">{passport.cleaned_sha256}</code>
          <div style="margin-top:14px;font-size:0.72rem;color:#3A5880;display:flex;justify-content:space-between;">
            <span>Security Seal: <code>{passport.integrity_signature}</code></span>
            <span>✓ Cryptographically Signed & Verified</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────────────────────────────────────
# MODULE 8: AUDIT LEDGER & TIME MACHINE
# ─────────────────────────────────────────────────────────────────────────────

elif st.session_state.selected_nav == "Audit Ledger & Time Machine":
    st.subheader("Audit Ledger & Dataset Time Machine")
    col_u, col_sp = st.columns([1, 3])
    with col_u:
        if st.button("↩ Undo Last Action", disabled=len(sm._undo_stack) == 0, use_container_width=True):
            event = sm.undo_last_action()
            if event:
                st.toast(f"Undid event: {event.undo_of}", icon="↩")
                st.rerun()

    audit_rows = [
        {
            "Event ID": e.event_id,
            "Timestamp UTC": e.timestamp_utc,
            "Revision": f"{e.dataset_revision_before} → {e.dataset_revision_after}",
            "Decision": e.decision.upper(),
            "Rule ID": e.rule_id,
            "Changed": e.items_changed,
            "Reason": e.reason,
        }
        for e in sm.audit_events
    ]
    st.dataframe(pd.DataFrame(audit_rows), hide_index=True, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# MODULE 9: TRUST VAULT & EXPORTS
# ─────────────────────────────────────────────────────────────────────────────

elif st.session_state.selected_nav == "Trust Vault":
    st.subheader("Trust Vault & Verified Exports")
    st.markdown(
        """
        <div class="ct-card">
          <div style="font-weight:700;font-size:1rem;color:#0F1D35;margin-bottom:6px;">OWASP ASVS 5.0 Security Profile</div>
          <p style="font-size:0.84rem;color:#3A5880;line-height:1.5;">
            ClearTrace enforces strict local-first memory bounds, session isolation, and formula injection sanitization.
            All exported CSV files have dangerous formula prefixes (=, @, non-numeric +, -) neutralized with a leading single quote.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.download_button(
            "📥 Cleaned CSV (Formula-Safe)",
            data=export_cleaned_csv(sm.working_df, escape_formulas=True),
            file_name=f"cleartrace_cleaned_{sm.filename}",
            mime="text/csv",
            use_container_width=True,
            type="primary",
        )
    with c2:
        st.download_button(
            "📄 Findings Report CSV",
            data=export_findings_report(findings),
            file_name=f"cleartrace_findings_{sm.filename}",
            mime="text/csv",
            use_container_width=True,
        )
    with c3:
        st.download_button(
            "📜 Audit Log CSV",
            data=export_audit_log(sm.audit_events),
            file_name=f"cleartrace_audit_{sm.filename}",
            mime="text/csv",
            use_container_width=True,
        )
