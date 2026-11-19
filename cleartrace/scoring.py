"""ClearTrace — Transparent Quality Score and Repair Prioritization Engine.

Mathematical, deterministic, and fully explainable scoring without black-box or invented numbers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple
import pandas as pd

from cleartrace.models import Finding, QualityMetrics


@dataclass
class ScoreComponent:
    name: str
    weight_pct: int
    raw_score: float  # 0 to 100
    weighted_score: float
    deductions: float
    explanation: str


@dataclass
class QualityScoreReport:
    overall_score: float  # 0 to 100
    grade: str  # A+, A, B, C, D, F
    components: List[ScoreComponent]
    summary: str


def calculate_quality_score(frame: pd.DataFrame, findings: List[Finding]) -> QualityScoreReport:
    """Calculates a transparent, weighted Data Quality Score (0-100) grounded in mathematical metrics.

    Components:
    1. Completeness (35% weight): Ratio of non-missing cells.
    2. Uniqueness (25% weight): Absence of exact duplicate rows.
    3. Structural Validity (25% weight): Absence of date/numeric format violations.
    4. Consistency (15% weight): Absence of whitespace padding and category variants.
    """
    total_rows = len(frame)
    total_cols = len(frame.columns)
    total_cells = max(1, total_rows * total_cols)

    if frame.empty:
        return QualityScoreReport(
            overall_score=100.0,
            grade="A+",
            components=[],
            summary="Empty dataset carries no measured defects.",
        )

    # 1. Completeness
    missing_cells = sum(f.affected_count for f in findings if f.rule_id == "missing-values")
    completeness_ratio = max(0.0, 1.0 - (missing_cells / total_cells))
    completeness_score = round(completeness_ratio * 100.0, 1)

    # 2. Uniqueness
    dup_rows = sum(f.affected_count for f in findings if f.rule_id == "duplicate-rows")
    uniqueness_ratio = max(0.0, 1.0 - (dup_rows / total_rows))
    uniqueness_score = round(uniqueness_ratio * 100.0, 1)

    # 3. Validity (dates, non-numeric strings in numeric columns)
    invalid_dates = sum(f.affected_count for f in findings if f.rule_id == "invalid-dates")
    invalid_numbers = sum(f.affected_count for f in findings if f.rule_id == "invalid-numbers")
    validity_defects = invalid_dates + invalid_numbers
    validity_ratio = max(0.0, 1.0 - (validity_defects / total_cells))
    validity_score = round(validity_ratio * 100.0, 1)

    # 4. Consistency (whitespace, category variants)
    whitespace_count = sum(f.affected_count for f in findings if f.rule_id == "trim-whitespace")
    category_count = sum(f.affected_count for f in findings if f.rule_id == "category-variants")
    consistency_defects = whitespace_count + category_count
    consistency_ratio = max(0.0, 1.0 - (consistency_defects / total_cells))
    consistency_score = round(consistency_ratio * 100.0, 1)

    # Weighted Sum
    c_weight = 0.35
    u_weight = 0.25
    v_weight = 0.25
    k_weight = 0.15

    weighted_c = completeness_score * c_weight
    weighted_u = uniqueness_score * u_weight
    weighted_v = validity_score * v_weight
    weighted_k = consistency_score * k_weight

    overall = round(weighted_c + weighted_u + weighted_v + weighted_k, 1)

    # Letter Grade
    if overall >= 95.0:
        grade = "A+"
    elif overall >= 90.0:
        grade = "A"
    elif overall >= 80.0:
        grade = "B"
    elif overall >= 70.0:
        grade = "C"
    elif overall >= 60.0:
        grade = "D"
    else:
        grade = "F"

    components = [
        ScoreComponent(
            name="Completeness",
            weight_pct=35,
            raw_score=completeness_score,
            weighted_score=round(weighted_c, 1),
            deductions=round(35.0 - weighted_c, 1),
            explanation=f"{missing_cells} missing cell{'s' if missing_cells != 1 else ''} out of {total_cells:,} total cells.",
        ),
        ScoreComponent(
            name="Uniqueness",
            weight_pct=25,
            raw_score=uniqueness_score,
            weighted_score=round(weighted_u, 1),
            deductions=round(25.0 - weighted_u, 1),
            explanation=f"{dup_rows} exact duplicate row{'s' if dup_rows != 1 else ''} out of {total_rows:,} rows.",
        ),
        ScoreComponent(
            name="Structural Validity",
            weight_pct=25,
            raw_score=validity_score,
            weighted_score=round(weighted_v, 1),
            deductions=round(25.0 - weighted_v, 1),
            explanation=f"{validity_defects} syntax/schema format defect{'s' if validity_defects != 1 else ''} detected.",
        ),
        ScoreComponent(
            name="Consistency",
            weight_pct=15,
            raw_score=consistency_score,
            weighted_score=round(weighted_k, 1),
            deductions=round(15.0 - weighted_k, 1),
            explanation=f"{consistency_defects} whitespace or category variant anomaly cells detected.",
        ),
    ]

    summary = (
        f"Overall Quality Score is {overall}/100 (Grade {grade}). "
        f"Strongest area: {max(components, key=lambda c: c.raw_score).name} ({max(components, key=lambda c: c.raw_score).raw_score}%). "
        f"Primary deduction: {max(components, key=lambda c: c.deductions).name} (-{max(components, key=lambda c: c.deductions).deductions} pts)."
    )

    return QualityScoreReport(
        overall_score=overall,
        grade=grade,
        components=components,
        summary=summary,
    )


def rank_proposals(findings: List[Finding]) -> List[Tuple[Finding, float, str]]:
    """Ranks actionable repair proposals by transparent priority score.

    Priority formula:
    Priority = Severity Base (High=30, Med=20, Low=10) * log(1 + affected_count) * Confidence Factor (1.0)
    """
    severity_map = {"High": 30.0, "Medium": 20.0, "Review": 15.0, "Low": 10.0}
    ranked = []

    for f in findings:
        if not f.action:
            continue
        base = severity_map.get(f.risk, 10.0)
        vol_multiplier = 1.0 + math.log1p(f.affected_count)
        priority_score = round(base * vol_multiplier, 1)
        reason = f"Severity '{f.risk}' (weight {base:.0f}) × volume log-factor ({vol_multiplier:.2f})"
        ranked.append((f, priority_score, reason))

    # Sort descending by priority score
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked
