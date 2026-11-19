from __future__ import annotations

import io
import json
import pytest
from fastapi.testclient import TestClient

from server import app

client = TestClient(app)


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "OWASP ASVS" in data["security_profile"]


def test_dataset_demo_and_summary():
    res = client.post("/api/dataset/demo")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["total_rows"] == 7

    summary_res = client.get("/api/dataset/summary")
    assert summary_res.status_code == 200
    s_data = summary_res.json()
    assert s_data["rows"] == 7
    assert "id" in s_data["columns"]
    assert s_data["metrics"]["duplicate_rows"] == 1


def test_quality_score_endpoint():
    res = client.get("/api/quality/score")
    assert res.status_code == 200
    data = res.json()
    assert "overall_score" in data
    assert "grade" in data
    assert len(data["components"]) == 4


def test_findings_and_proposals():
    f_res = client.get("/api/quality/findings")
    assert f_res.status_code == 200
    findings = f_res.json()
    assert len(findings) >= 5

    p_res = client.get("/api/repair/proposals")
    assert p_res.status_code == 200
    proposals = p_res.json()
    assert len(proposals) >= 2
    # Ensure prioritized
    assert proposals[0]["priority_score"] >= proposals[-1]["priority_score"]
    assert "impact_simulation" in proposals[0]


def test_repair_apply_and_stale_rejection():
    # Reload demo
    client.post("/api/dataset/demo")
    summary = client.get("/api/dataset/summary").json()
    cur_rev = summary["revision"]

    p_res = client.get("/api/repair/proposals").json()
    prop = p_res[0]

    # Apply
    apply_res = client.post("/api/repair/apply", json={
        "finding_id": prop["finding_id"],
        "expected_revision": cur_rev,
    })
    assert apply_res.status_code == 200
    new_rev = apply_res.json()["revision"]
    assert new_rev == cur_rev + 1

    # Stale attempt must return 409 Conflict
    stale_res = client.post("/api/repair/apply", json={
        "finding_id": prop["finding_id"],
        "expected_revision": cur_rev,
    })
    assert stale_res.status_code == 409


def test_timemachine_compare_and_restore():
    client.post("/api/dataset/demo")
    timeline = client.get("/api/timemachine/timeline").json()
    assert len(timeline) >= 1

    # Compare initial revision with itself
    comp = client.post("/api/timemachine/compare", json={"rev_from": 1, "rev_to": 1}).json()
    assert comp["rows_before"] == 7
    assert comp["rows_after"] == 7


def test_undo_and_reset_endpoints():
    client.post("/api/dataset/demo")
    summary = client.get("/api/dataset/summary").json()
    cur_rev = summary["revision"]

    # Apply a repair
    props = client.get("/api/repair/proposals").json()
    client.post("/api/repair/apply", json={"finding_id": props[0]["finding_id"], "expected_revision": cur_rev})

    # Undo
    undo_res = client.post("/api/audit/undo")
    assert undo_res.status_code == 200

    # Reset
    reset_res = client.post("/api/audit/reset")
    assert reset_res.status_code == 200
    assert reset_res.json()["rows"] == 7


def test_passport_generation():
    client.post("/api/dataset/demo")
    pass_res = client.get("/api/passport")
    assert pass_res.status_code == 200
    p = pass_res.json()
    assert p["passport_id"].startswith("CT-PASS-")
    assert len(p["original_sha256"]) == 64
    assert len(p["cleaned_sha256"]) == 64
    assert p["integrity_signature"].startswith("SHA256:")


def test_export_endpoints():
    client.post("/api/dataset/demo")
    csv_res = client.get("/api/export/cleaned")
    assert csv_res.status_code == 200
    assert csv_res.headers["content-type"].startswith("text/csv")
    assert "'=2+3" in csv_res.text  # Formula injection escaped

    find_res = client.get("/api/export/findings")
    assert find_res.status_code == 200

    audit_res = client.get("/api/export/audit")
    assert audit_res.status_code == 200

    pass_json = client.get("/api/export/passport")
    assert pass_json.status_code == 200
    assert "CT-PASS-" in pass_json.text


def test_spa_and_manifest():
    index_res = client.get("/")
    assert index_res.status_code == 200
    assert "ClearTrace" in index_res.text
    assert "mobile-nav" in index_res.text
    assert "connectivity-banner" in index_res.text

    # Verify both /static/manifest.json and root /manifest.json
    for path in ["/static/manifest.json", "/manifest.json"]:
        man_res = client.get(path)
        assert man_res.status_code == 200
        manifest = man_res.json()
        assert manifest["name"] == "ClearTrace"
        assert manifest["short_name"] == "ClearTrace"
        assert manifest["display"] == "standalone"
        assert manifest["scope"] == "/"
        purposes = [icon.get("purpose") for icon in manifest["icons"]]
        assert "maskable" in purposes
        assert "any" in purposes

    # Verify root Service Worker with allowed scope header
    sw_res = client.get("/sw.js")
    assert sw_res.status_code == 200
    assert sw_res.headers.get("Service-Worker-Allowed") == "/"
    assert "startsWith('/api/')" in sw_res.text

    # Verify offline fallback page and apple touch icon
    assert client.get("/static/offline.html").status_code == 200
    assert client.get("/apple-touch-icon.png").status_code == 200



def test_math_rules_crud_endpoints():
    token = "test-math-rules-token-111"
    # Upload test data
    csv_bytes = b"dept,rev,cogs,profit\nEng,100,40,60\nMkt,200,80,150\n"
    client.post(
        "/api/dataset/upload",
        files={"file": ("dept_fin.csv", io.BytesIO(csv_bytes), "text/csv")},
        headers={"X-Session-ID": token},
    )

    # 1. Initially no custom rules
    rules_res = client.get("/api/math/rules", headers={"X-Session-ID": token})
    assert rules_res.status_code == 200
    assert len(rules_res.json()) == 0

    # 2. Add custom formula rule: profit = rev - cogs
    add_res = client.post(
        "/api/math/rules",
        json={
            "rule_id": "profit_formula",
            "rule_type": "formula",
            "target_column": "profit",
            "expression": "rev - cogs",
            "description": "Profit must equal rev minus cogs.",
        },
        headers={"X-Session-ID": token},
    )
    assert add_res.status_code == 200
    data = add_res.json()
    assert data["success"] is True
    assert data["total_rules"] == 1
    # Row 2 (Mkt) has rev 200, cogs 80 -> expected 120, but recorded is 150 (diff +30)
    assert data["total_math_issues"] == 1

    # 3. GET /api/math/rules shows the rule
    check_rules = client.get("/api/math/rules", headers={"X-Session-ID": token}).json()
    assert len(check_rules) == 1
    assert check_rules[0]["rule_id"] == "profit_formula"
    assert check_rules[0]["expression"] == "rev - cogs"

    # 4. Delete the rule
    del_res = client.delete("/api/math/rules/profit_formula", headers={"X-Session-ID": token})
    assert del_res.status_code == 200
    assert del_res.json()["deleted_rule_id"] == "profit_formula"
    assert del_res.json()["total_rules"] == 0


def test_comparison_summary_endpoint():
    """Feature C: Verify real before/after quality comparison between revisions."""
    token = "test-comparison-token-777"
    client.post("/api/dataset/demo", headers={"X-Session-ID": token})

    # Initially revision 1: baseline score == current score
    res = client.get("/api/comparison/summary", headers={"X-Session-ID": token})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["revision_baseline"] == 1
    assert data["revision_current"] == 1
    assert data["score_delta"] == 0.0

    # Apply a repair mutation (advancing revision from 1 to 2)
    props = client.get("/api/repair/proposals", headers={"X-Session-ID": token}).json()
    assert len(props) > 0
    client.post(
        "/api/repair/apply",
        json={"finding_id": props[0]["finding_id"], "expected_revision": 1},
        headers={"X-Session-ID": token},
    )

    # Re-check comparison summary: revision 2, score delta calculated from real data
    res_after = client.get("/api/comparison/summary", headers={"X-Session-ID": token})
    assert res_after.status_code == 200
    data_after = res_after.json()
    assert data_after["revision_current"] == 2
    assert data_after["total_repairs_applied"] == 1
    assert data_after["score_after"] >= data_after["score_before"]


def test_export_executive_report_endpoint():
    """Feature D: Verify executive data quality report generation in Markdown and JSON formats."""
    token = "test-report-token-888"
    client.post("/api/dataset/demo", headers={"X-Session-ID": token})

    # 1. Markdown export
    md_res = client.get("/api/export/report?format=markdown", headers={"X-Session-ID": token})
    assert md_res.status_code == 200
    assert "text/markdown" in md_res.headers["content-type"]
    text = md_res.text
    assert "# ClearTrace — Executive Data Quality & Audit Assessment Report" in text
    assert "Dataset Identity & Cryptographic Provenance" in text
    assert "Transparent Data Hygiene Score" in text
    assert "Deterministic Mathematical Intelligence Audit" in text

    # 2. JSON structured export
    json_res = client.get("/api/export/report?format=json", headers={"X-Session-ID": token})
    assert json_res.status_code == 200
    jdata = json_res.json()
    assert jdata["success"] is True
    assert "report_markdown" in jdata
    assert "score" in jdata
    assert "passport_id" in jdata

