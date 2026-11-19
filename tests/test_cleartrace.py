from __future__ import annotations

import io
import pytest
import pandas as pd

from cleartrace.ingest import parse_csv_bytes, load_demo_dataset, IngestionError
from cleartrace.scan import scan_dataset
from cleartrace.repair import generate_proposal, apply_repair
from cleartrace.audit import SessionManager, StaleRevisionError
from cleartrace.export import export_cleaned_csv, export_findings_report, export_audit_log, sanitize_cell_for_csv


def test_ingest_validation():
    # Empty bytes test
    with pytest.raises(IngestionError, match="empty"):
        parse_csv_bytes(b"")

    # Valid CSV parsing
    csv_data = b"id,name,score\n1,Alice,95\n2,Bob,88\n"
    df, meta = parse_csv_bytes(csv_data, filename="test.csv")
    assert len(df) == 2
    assert meta["total_rows"] == 2
    assert meta["total_columns"] == 3
    assert list(df.columns) == ["id", "name", "score"]


def test_demo_dataset():
    demo = load_demo_dataset()
    assert len(demo) == 7
    assert "salary" in demo.columns
    assert "city" in demo.columns


def test_scan_synthetic_dataset():
    # Load synthetic dataset from samples
    demo = load_demo_dataset()
    findings, metrics = scan_dataset(demo)

    assert metrics.total_rows == 7
    assert metrics.total_columns == 7
    assert metrics.duplicate_rows == 1
    assert metrics.missing_cells >= 1

    rule_ids = {f.rule_id for f in findings}
    assert "duplicate-rows" in rule_ids
    assert "missing-values" in rule_ids
    assert "trim-whitespace" in rule_ids
    assert "category-variants" in rule_ids
    assert "invalid-dates" in rule_ids
    assert "invalid-numbers" in rule_ids
    assert "numeric-outliers" in rule_ids


def test_repair_lifecycle():
    demo = load_demo_dataset()
    session = SessionManager(demo, filename="synthetic.csv")
    assert session.dataset_revision == 1

    findings, _ = scan_dataset(session.working_df)
    whitespace_finding = next(f for f in findings if f.rule_id == "trim-whitespace")

    # Generate proposal
    prop = generate_proposal(whitespace_finding, session.working_df)
    assert len(prop.diff_sample) > 0
    assert prop.diff_sample[0].column == "city"
    assert prop.diff_sample[0].before == " Bengaluru "
    assert prop.diff_sample[0].after == "Bengaluru"

    # Apply proposal
    event = session.apply_proposal(prop, expected_revision=1)
    assert session.dataset_revision == 2
    assert event.decision == "approved"
    assert session.working_df.loc[0, "city"] == "Bengaluru"

    # Rescan should show whitespace finding resolved for that cell
    new_findings, _ = scan_dataset(session.working_df)
    new_whitespace = [f for f in new_findings if f.rule_id == "trim-whitespace"]
    assert len(new_whitespace) == 0


def test_stale_revision_protection():
    demo = load_demo_dataset()
    session = SessionManager(demo)

    findings, _ = scan_dataset(session.working_df)
    ws_finding = next(f for f in findings if f.rule_id == "trim-whitespace")
    prop = generate_proposal(ws_finding, session.working_df)

    # First apply succeeds
    session.apply_proposal(prop, expected_revision=1)
    assert session.dataset_revision == 2

    # Attempting to re-apply with stale revision 1 must raise StaleRevisionError
    with pytest.raises(StaleRevisionError):
        session.apply_proposal(prop, expected_revision=1)


def test_undo_and_reset():
    demo = load_demo_dataset()
    session = SessionManager(demo)

    findings, _ = scan_dataset(session.working_df)
    ws_finding = next(f for f in findings if f.rule_id == "trim-whitespace")
    prop = generate_proposal(ws_finding, session.working_df)

    session.apply_proposal(prop, expected_revision=1)
    assert session.working_df.loc[0, "city"] == "Bengaluru"

    # Undo
    undo_event = session.undo_last_action()
    assert undo_event is not None
    assert undo_event.decision == "undone"
    assert session.working_df.loc[0, "city"] == " Bengaluru "
    assert session.dataset_revision == 3

    # Reset
    reset_event = session.reset_to_original()
    assert reset_event.decision == "reset"
    assert session.working_df.equals(session.original_df)


def test_formula_injection_guard():
    assert sanitize_cell_for_csv("=2+3") == "'=2+3"
    assert sanitize_cell_for_csv("@SUM(A1)") == "'@SUM(A1)"
    assert sanitize_cell_for_csv("+CMD") == "'+CMD"
    # Valid numbers must not be corrupted
    assert sanitize_cell_for_csv("-42") == "-42"
    assert sanitize_cell_for_csv("+10.5") == "+10.5"
    assert sanitize_cell_for_csv("Normal Text") == "Normal Text"

    demo = load_demo_dataset()
    csv_bytes = export_cleaned_csv(demo, escape_formulas=True)
    decoded = csv_bytes.decode("utf-8-sig")
    assert "'=2+3" in decoded


def test_export_reports():
    demo = load_demo_dataset()
    findings, _ = scan_dataset(demo)
    session = SessionManager(demo)

    findings_csv = export_findings_report(findings)
    assert len(findings_csv) > 0
    assert b"Finding ID" in findings_csv

    audit_csv = export_audit_log(session.audit_events)
    assert len(audit_csv) > 0
    assert b"Event ID" in audit_csv
