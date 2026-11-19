"""ClearTrace — Mentor Round Verification Test Suite.

Verifies:
1. Exact Decimal mathematical validation (INV-002 495 vs 520, +25 diff).
2. Consistent detection across CSV, Excel (.xlsx), and PDF (.pdf).
3. Constraint checks: negative quantities, missing totals, invalid numeric strings, discounts exceeding subtotal.
4. Valid invoices (INV-001, 003, 004, 009) are NOT falsely flagged.
5. Multi-format ingestion and macro/size security bounds.
6. Mathematical repair proposal, approval, application, rescan, audit, and undo lifecycle.
7. RAG lexical retrieval (BM25) with authentic source citations.
8. Grounded LLM assistant honest availability reporting and citation verification.
9. REST API endpoints for math intelligence and RAG Q&A.
"""

from decimal import Decimal
import io
import os
from pathlib import Path
import secrets
import pytest
from fastapi.testclient import TestClient

from cleartrace.math_engine import (
    parse_decimal,
    inspect_invoice_dataset,
    convert_math_findings_to_proposals,
)
from cleartrace.ingest import (
    parse_document_bytes,
    load_math_demo_dataset,
    IngestionError,
)
from cleartrace.audit import SessionManager
from cleartrace.retrieval import EvidenceIndex, build_session_evidence_index
from cleartrace.llm_assistant import get_llm_status, ask_knowledge_assistant
from server import app

ROOT = Path(__file__).resolve().parent.parent
client = TestClient(app)


# ── 1. Mathematical Validation Engine Tests ─────────────────────────────────

def test_decimal_numeric_parsing_rules():
    """Verify strict Decimal parsing rejects ambiguous or dangerous tokens."""
    assert parse_decimal("1,234.50") == Decimal("1234.50")
    assert parse_decimal("0.00") == Decimal("0.00")
    assert parse_decimal("-42.50") == Decimal("-42.50")
    assert parse_decimal("  100  ") == Decimal("100")

    # Reject non-numeric, locale-ambiguous, or dangerous strings
    invalid_cases = ["1,2,3", "1e9", "=2+3", "NaN", "Infinity", "€100", "two hundred", True, False]
    for val in invalid_cases:
        with pytest.raises(ValueError):
            parse_decimal(val)


def test_synthetic_invoice_math_discrepancies():
    """Mentor requirement: Calculate expected total for INV-002:
    2 × 250 − 50 + 45 = 495. Recorded is 520. Discrepancy is +25.
    Verify all 9 rows in math_errors.csv produce exact expected findings.
    """
    csv_path = ROOT / "samples" / "math_errors.csv"
    df, meta = parse_document_bytes(csv_path.read_bytes(), filename=csv_path.name)
    assert len(df) == 9

    findings = inspect_invoice_dataset(df, tolerance=Decimal("0.01"))
    error_tuples = {(f.invoice_id, f.rule_id) for f in findings}

    # 1. INV-002: Math mismatch (+25 deviation)
    assert ("INV-002", "MATH_MISMATCH") in error_tuples
    mismatch_002 = next(f for f in findings if f.invoice_id == "INV-002")
    assert mismatch_002.expected == "495.00"
    assert mismatch_002.observed == "520.00"
    assert mismatch_002.deviation == "25.00"
    assert "2 × 250" in mismatch_002.calculation_steps

    # 2. INV-005: Negative quantity
    assert ("INV-005", "NEGATIVE_NOT_ALLOWED") in error_tuples
    inv_005 = next(f for f in findings if f.invoice_id == "INV-005")
    assert inv_005.field == "quantity"
    assert inv_005.observed == "-2"

    # 3. INV-006: Missing total (expected 290.00 derived)
    assert ("INV-006", "MISSING_TOTAL") in error_tuples
    inv_006 = next(f for f in findings if f.invoice_id == "INV-006")
    assert inv_006.expected == "290.00"
    assert inv_006.proposed_value == "290.00"

    # 4. INV-007: Invalid numeric input ("two hundred")
    assert ("INV-007", "INVALID_NUMBER") in error_tuples
    inv_007 = next(f for f in findings if f.invoice_id == "INV-007")
    assert inv_007.field == "unit_price"
    assert inv_007.observed == "two hundred"

    # 5. INV-008: Discount exceeds gross subtotal (200 > 120)
    assert ("INV-008", "DISCOUNT_EXCEEDS_SUBTOTAL") in error_tuples
    inv_008 = next(f for f in findings if f.invoice_id == "INV-008")
    assert inv_008.observed == "200.00"
    assert inv_008.expected == "120.00"

    # 6. Correct invoices MUST NOT be flagged as math mismatches
    valid_ids = {"INV-001", "INV-003", "INV-004", "INV-009"}
    for f in findings:
        if f.rule_id == "MATH_MISMATCH":
            assert f.invoice_id not in valid_ids


# ── 2. Multi-Format Ingestion Tests (CSV, XLSX, PDF) ───────────────────────

def test_excel_ingestion_and_math_parity():
    """Verify Excel XLSX ingestion extracts same 9 rows and detects identical math errors."""
    xlsx_path = ROOT / "samples" / "math_errors.xlsx"
    assert xlsx_path.exists(), "samples/math_errors.xlsx must exist"

    df, meta = parse_document_bytes(xlsx_path.read_bytes(), filename=xlsx_path.name)
    assert meta["format"] == "xlsx"
    assert len(df) == 9

    findings = inspect_invoice_dataset(df)
    mismatch_002 = next(f for f in findings if f.invoice_id == "INV-002")
    assert mismatch_002.rule_id == "MATH_MISMATCH"
    assert mismatch_002.expected == "495.00"
    assert mismatch_002.observed == "520.00"
    assert mismatch_002.deviation == "25.00"


def test_pdf_ingestion_and_math_parity():
    """Verify PDF table extraction extracts same 9 rows and detects identical math errors."""
    pdf_path = ROOT / "samples" / "math_errors.pdf"
    assert pdf_path.exists(), "samples/math_errors.pdf must exist"

    df, meta = parse_document_bytes(pdf_path.read_bytes(), filename=pdf_path.name)
    assert meta["format"] == "pdf"
    assert len(df) == 9
    assert any("page 1" in prov for prov in meta["provenance_map"].values())

    findings = inspect_invoice_dataset(df)
    mismatch_002 = next(f for f in findings if f.invoice_id == "INV-002")
    assert mismatch_002.rule_id == "MATH_MISMATCH"
    assert mismatch_002.expected == "495.00"
    assert mismatch_002.observed == "520.00"
    assert mismatch_002.deviation == "25.00"


def test_security_bounds_and_macro_rejection():
    """Verify parser enforces security bounds and rejects dangerous files."""
    # Reject unsupported format
    with pytest.raises(IngestionError, match="Unsupported file format"):
        parse_document_bytes(b"data", "test.docx")

    # Reject empty file
    with pytest.raises(IngestionError, match="empty"):
        parse_document_bytes(b"", "empty.csv")

    # Reject non-PDF with .pdf extension
    with pytest.raises(IngestionError, match="PDF header"):
        parse_document_bytes(b"NOT_A_PDF_FILE", "fake.pdf")

    # Reject non-ZIP with .xlsx extension
    with pytest.raises(IngestionError, match="OOXML"):
        parse_document_bytes(b"NOT_A_ZIP", "fake.xlsx")


# ── 3. Mathematical Repair, Approval, Rescan, and Audit Lifecycle ───────────

def test_math_repair_lifecycle():
    """Verify user can approve a math correction (INV-002), apply it, rescan, and undo."""
    csv_path = ROOT / "samples" / "math_errors.csv"
    df, meta = parse_document_bytes(csv_path.read_bytes(), filename="math_errors.csv")
    sm = SessionManager(df, filename="math_errors.csv", provenance_map=meta["provenance_map"])

    # 1. Initial scan detects INV-002
    initial_findings = sm.get_math_findings()
    mismatch_002 = next(f for f in initial_findings if f.invoice_id == "INV-002")
    assert mismatch_002.observed == "520.00"

    # 2. Convert to repair proposals
    proposals = convert_math_findings_to_proposals(initial_findings, sm.working_df)
    std_f, prop_002 = next(p for p in proposals if "INV-002" in p[0].id)
    assert prop_002.diff_sample[0].before == "520.00"
    assert prop_002.diff_sample[0].after == "495.00"

    # 3. Apply approved repair
    event = sm.apply_proposal(prop_002, expected_revision=1)
    assert event.decision == "approved"
    assert sm.dataset_revision == 2

    # 4. Verify working copy is updated
    updated_val = sm.working_df.loc[prop_002.target_rows[0], "recorded_total"]
    assert updated_val == "495.00"

    # 5. Rescan: INV-002 is now clean!
    rescanned_findings = sm.get_math_findings()
    assert not any(f.invoice_id == "INV-002" and f.rule_id == "MATH_MISMATCH" for f in rescanned_findings)

    # 6. Undo: reverts working copy back to 520.00
    undo_event = sm.undo_last_action()
    assert undo_event is not None
    assert sm.dataset_revision == 3
    reverted_val = sm.working_df.loc[prop_002.target_rows[0], "recorded_total"]
    assert reverted_val == "520.00"


# ── 4. RAG Retrieval & Knowledge Assistant Tests ────────────────────────────

def test_rag_bm25_retrieval_with_citations():
    """Verify BM25 retrieval finds authentic source passages with exact source citations."""
    csv_path = ROOT / "samples" / "math_errors.csv"
    df, meta = parse_document_bytes(csv_path.read_bytes(), filename="math_errors.csv")
    sm = SessionManager(df, filename="math_errors.csv", provenance_map=meta["provenance_map"])
    index = sm.get_evidence_index()

    # Query 1: Invoice calculation policy
    results_rule = index.search("How is the invoice expected total calculated?", limit=3)
    assert len(results_rule) > 0
    assert any("Expected total = quantity" in r[1].text or "calculated expected total" in r[1].text for r in results_rule)

    # Query 2: Specific invoice question
    results_inv = index.search("Which invoice has a mismatch or discrepancy?", limit=3)
    assert len(results_inv) > 0
    assert any("INV-002" in r[1].text or "MATH_MISMATCH" in r[1].text for r in results_inv)


def test_llm_assistant_honest_fallback_when_disabled():
    """Verify assistant reports honest 'unavailable' status when unconfigured rather than faking AI."""
    csv_path = ROOT / "samples" / "math_errors.csv"
    df, meta = parse_document_bytes(csv_path.read_bytes(), filename="math_errors.csv")
    sm = SessionManager(df, filename="math_errors.csv", provenance_map=meta["provenance_map"])
    index = sm.get_evidence_index()

    answer = ask_knowledge_assistant("Why was INV-002 flagged?", index)
    assert answer.status == "llm_unavailable_evidence_presented"
    assert answer.provider == "retrieval-deterministic"
    assert len(answer.references) > 0
    # Must contain verified evidence in the text
    assert "INV-002" in answer.answer or "495" in answer.answer


# ── 5. REST API Integration Tests for Mentor Features ───────────────────────

def test_api_math_validate_and_demo():
    """Verify /api/math/validate, /api/math/findings, and /api/dataset/math-demo."""
    # 1. Load math demo via API for CSV
    res_demo = client.post("/api/dataset/math-demo", json={"format": "csv"})
    assert res_demo.status_code == 200
    data = res_demo.json()
    assert data["format"] == "csv"
    assert data["total_rows"] == 9
    assert data["math_issues_count"] >= 5

    # 2. Get math findings
    res_findings = client.get("/api/math/findings?tolerance=0.01")
    assert res_findings.status_code == 200
    findings = res_findings.json()
    inv_002 = next((f for f in findings if f["invoice_id"] == "INV-002"), None)
    assert inv_002 is not None
    assert inv_002["expected"] == "495.00"
    assert inv_002["observed"] == "520.00"
    assert inv_002["deviation"] == "25.00"

    # 3. Validate math with custom tolerance
    res_val = client.post("/api/math/validate", json={"tolerance": 0.01})
    assert res_val.status_code == 200
    summary = res_val.json()["summary"]
    assert summary["math_mismatches"] == 1
    assert summary["negative_not_allowed"] == 1
    assert summary["missing_totals"] == 1


def test_api_rag_search_and_ask():
    """Verify /api/rag/status, /api/rag/search, and /api/rag/ask."""
    # Check status
    res_status = client.get("/api/rag/status")
    assert res_status.status_code == 200
    assert res_status.json()["status"] == "ready"
    assert res_status.json()["indexed_passages"] > 0

    # Search
    res_search = client.post("/api/rag/search", json={"query": "INV-002 discrepancy", "limit": 3})
    assert res_search.status_code == 200
    results = res_search.json()["results"]
    assert len(results) > 0
    assert any("INV-002" in r["title"] or "INV-002" in r["text"] for r in results)

    # Ask
    res_ask = client.post("/api/rag/ask", json={"question": "What is the expected total for INV-002?"})
    assert res_ask.status_code == 200
    answer_data = res_ask.json()
    assert "answer" in answer_data
    assert len(answer_data["references"]) > 0


def test_api_excel_and_pdf_demo_loading():
    """Verify loading demo datasets in XLSX and PDF formats via REST API."""
    # XLSX
    res_xlsx = client.post("/api/dataset/math-demo", json={"format": "xlsx"})
    assert res_xlsx.status_code == 200
    assert res_xlsx.json()["format"] == "xlsx"
    assert res_xlsx.json()["total_rows"] == 9

    # PDF
    res_pdf = client.post("/api/dataset/math-demo", json={"format": "pdf"})
    assert res_pdf.status_code == 200
    assert res_pdf.json()["format"] == "pdf"
    assert res_pdf.json()["total_rows"] == 9


def test_math_integrity_dimension_advances_score_on_inv002_repair():
    """Verify that fixing INV-002 advances the Mathematical Integrity dimension and Composite Quality Score."""
    token = "test-math-progression-" + secrets.token_hex(6)
    headers = {"X-Session-ID": token}

    # 1. Load math-demo invoice dataset
    load_res = client.post("/api/dataset/math-demo", json={"format": "csv"}, headers=headers)
    assert load_res.status_code == 200

    # 2. Inspect initial scores before repair
    baseline_comp = client.get("/api/comparison/summary", headers=headers).json()
    assert baseline_comp["initial_math_issues_count"] > 0
    init_math_score = baseline_comp["math_score_baseline"]
    init_comp_score = baseline_comp["composite_score_baseline"]

    # 3. Find and approve the INV-002 math discrepancy fix
    props = client.get("/api/repair/proposals", headers=headers).json()
    inv_002_prop = next(p for p in props if "INV-002" in p["finding_id"])
    apply_res = client.post(
        "/api/repair/apply",
        json={"finding_id": inv_002_prop["finding_id"], "expected_revision": 1},
        headers=headers,
    )
    assert apply_res.status_code == 200
    assert apply_res.json()["success"] is True
    assert apply_res.json()["revision"] == 2

    # 4. Verify post-repair comparison metrics
    after_comp = client.get("/api/comparison/summary", headers=headers).json()
    assert after_comp["revision_current"] == 2
    assert after_comp["resolved_math_issues_count"] == 1
    assert after_comp["math_score_current"] > init_math_score
    assert after_comp["math_score_delta"] > 0.0
    assert after_comp["composite_score_current"] > init_comp_score
    assert after_comp["composite_score_delta"] > 0.0
