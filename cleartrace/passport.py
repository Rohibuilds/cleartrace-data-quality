"""ClearTrace — Data Passport and Cryptographic Audit Verification.

Generates portable, tamper-evident quality passports with SHA-256 dataset hashing and detailed repair provenance.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List
import pandas as pd

from cleartrace.models import Finding, AuditEvent
from cleartrace.scoring import QualityScoreReport


@dataclass
class ImpactSimulation:
    proposal_id: str
    rule_id: str
    column: str
    cells_affected: int
    rows_affected: int
    data_loss_risk: str  # "None", "Low", "Medium", "High"
    resolved_issue_description: str
    side_effects: str


@dataclass
class DataPassport:
    passport_id: str
    issued_at_utc: str
    filename: str
    original_sha256: str
    cleaned_sha256: str
    total_rows: int
    total_columns: int
    quality_score: float
    grade: str
    completeness_pct: float
    repairs_applied_count: int
    unresolved_warnings_count: int
    audit_events_count: int
    score_breakdown: List[Dict[str, Any]]
    unresolved_findings: List[Dict[str, Any]]
    integrity_signature: str


def compute_df_sha256(df: pd.DataFrame) -> str:
    """Computes a deterministic SHA-256 digest of dataframe content."""
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    return hashlib.sha256(csv_bytes).hexdigest()


def simulate_impact(frame: pd.DataFrame, finding: Finding) -> ImpactSimulation:
    """Simulates the pre-mutation consequences of applying an actionable proposal."""
    action = finding.action
    col = finding.column
    count = finding.affected_count

    if action == "trim_whitespace":
        return ImpactSimulation(
            proposal_id=f"sim-{finding.id}",
            rule_id=finding.rule_id,
            column=col,
            cells_affected=count,
            rows_affected=count,
            data_loss_risk="Low",
            resolved_issue_description=f"Removes outer space characters from {count} text values in '{col}'.",
            side_effects="Preserves core text. Improves exact-match joins and string lookups.",
        )
    elif action == "normalize_categories":
        return ImpactSimulation(
            proposal_id=f"sim-{finding.id}",
            rule_id=finding.rule_id,
            column=col,
            cells_affected=count,
            rows_affected=count,
            data_loss_risk="Medium",
            resolved_issue_description=f"Standardizes case/spacing variants in '{col}' to the most frequent observed spelling.",
            side_effects="Merges minor spelling variations. Irreversible once exported without original snapshot.",
        )
    elif action == "remove_duplicates":
        return ImpactSimulation(
            proposal_id=f"sim-{finding.id}",
            rule_id=finding.rule_id,
            column="All columns",
            cells_affected=count * len(frame.columns),
            rows_affected=count,
            data_loss_risk="Medium",
            resolved_issue_description=f"Deletes {count} duplicate row(s), keeping the earliest instance.",
            side_effects="Permanent row reduction on working dataset. Verify identical rows are not valid repeated events.",
        )
    else:
        return ImpactSimulation(
            proposal_id=f"sim-{finding.id}",
            rule_id=finding.rule_id,
            column=col,
            cells_affected=0,
            rows_affected=0,
            data_loss_risk="None",
            resolved_issue_description="Manual review item. No automated mutation available.",
            side_effects="Requires human domain verification.",
        )


def generate_data_passport(
    original_df: pd.DataFrame,
    working_df: pd.DataFrame,
    filename: str,
    score_report: QualityScoreReport,
    findings: List[Finding],
    audit_events: List[AuditEvent],
) -> DataPassport:
    """Creates a cryptographic Data Passport certifying data hygiene and full audit history."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    orig_hash = compute_df_sha256(original_df)
    clean_hash = compute_df_sha256(working_df)

    applied_events = [e for e in audit_events if e.decision == "approved"]
    unresolved = [f for f in findings if f.risk in ("High", "Medium", "Review")]

    # Compute a deterministic passport seal
    seal_data = f"{filename}|{orig_hash}|{clean_hash}|{score_report.overall_score}|{len(applied_events)}"
    integrity_sig = hashlib.sha256(seal_data.encode("utf-8")).hexdigest()[:24].upper()
    passport_id = f"CT-PASS-{integrity_sig[:8]}"

    breakdown = [
        {
            "dimension": c.name,
            "weight": f"{c.weight_pct}%",
            "score": c.raw_score,
            "weighted": c.weighted_score,
            "explanation": c.explanation,
        }
        for c in score_report.components
    ]

    unresolved_summary = [
        {
            "category": f.kind,
            "column": f.column,
            "affected_records": f.affected_count,
            "risk": f.risk,
            "recommendation": f.recommendation,
        }
        for f in unresolved
    ]

    return DataPassport(
        passport_id=passport_id,
        issued_at_utc=now_str,
        filename=filename,
        original_sha256=orig_hash,
        cleaned_sha256=clean_hash,
        total_rows=len(working_df),
        total_columns=len(working_df.columns),
        quality_score=score_report.overall_score,
        grade=score_report.grade,
        completeness_pct=round(
            (1.0 - (sum(f.affected_count for f in findings if f.rule_id == "missing-values") / max(1, len(working_df) * len(working_df.columns)))) * 100.0,
            1,
        ),
        repairs_applied_count=len(applied_events),
        unresolved_warnings_count=len(unresolved),
        audit_events_count=len(audit_events),
        score_breakdown=breakdown,
        unresolved_findings=unresolved_summary,
        integrity_signature=f"SHA256:{integrity_sig}",
    )
