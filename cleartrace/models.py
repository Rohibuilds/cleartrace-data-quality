from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class Finding:
    """A quality issue detected in the dataset."""
    id: str
    rule_id: str
    kind: str
    column: str
    affected_count: int
    affected_row_indices: list[int]
    example: str
    explanation: str
    recommendation: str
    risk: str  # "High", "Medium", "Low", "Review"
    action: Optional[str] = None
    payload: Optional[dict[str, Any]] = None


@dataclass
class CellDiff:
    """A single cell mutation preview."""
    row_idx: int
    column: str
    before: Any
    after: Any


@dataclass
class RepairProposal:
    """A candidate non-mutating repair ready for explicit human review."""
    proposal_id: str
    finding_id: str
    rule_id: str
    column: str
    target_rows: list[int]
    before_summary: str
    after_summary: str
    diff_sample: list[CellDiff]
    risk: str
    explanation: str
    status: str = "Proposed"  # Proposed, Approved, Rejected, Applied


@dataclass
class AuditEvent:
    """Append-only audit record of an action in the session."""
    event_id: str
    timestamp_utc: str
    dataset_revision_before: int
    dataset_revision_after: int
    actor: str  # "user", "engine", "scanner", "system"
    decision: str  # "approved", "applied", "rejected", "undone", "reset"
    rule_id: str
    target_columns: list[str]
    target_rows: list[int]
    before_summary: str
    after_summary: str
    reason: str
    items_changed: int
    undo_of: Optional[str] = None

    @classmethod
    def create(
        cls,
        event_id: str,
        rev_before: int,
        rev_after: int,
        actor: str,
        decision: str,
        rule_id: str,
        target_columns: list[str],
        target_rows: list[int],
        before_summary: str,
        after_summary: str,
        reason: str,
        items_changed: int,
        undo_of: Optional[str] = None,
    ) -> AuditEvent:
        return cls(
            event_id=event_id,
            timestamp_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            dataset_revision_before=rev_before,
            dataset_revision_after=rev_after,
            actor=actor,
            decision=decision,
            rule_id=rule_id,
            target_columns=target_columns,
            target_rows=target_rows,
            before_summary=before_summary,
            after_summary=after_summary,
            reason=reason,
            items_changed=items_changed,
            undo_of=undo_of,
        )


@dataclass
class QualityMetrics:
    """High-level mathematical metrics describing the dataset quality."""
    total_rows: int
    total_columns: int
    total_cells: int
    completeness_pct: float
    missing_cells: int
    duplicate_rows: int
    format_violations: int
    review_count: int


@dataclass
class MathFinding:
    """A deterministic mathematical discrepancy or constraint violation."""
    id: str
    source_ref: str
    invoice_id: str
    rule_id: str
    severity: str
    field: str
    message: str
    observed: Optional[str] = None
    expected: Optional[str] = None
    deviation: Optional[str] = None
    calculation_steps: Optional[str] = None
    row_idx: int = 0
    action: Optional[str] = None
    proposed_value: Optional[str] = None


@dataclass
class Evidence:
    """An indexed passage with source provenance for RAG retrieval."""
    ref: str
    title: str
    text: str
    score: float = 0.0
    source_type: str = "row"


@dataclass
class GroundedAnswer:
    """An answer grounded in retrieved evidence."""
    answer: str
    references: list[str]
    provider: str
    status: str
    evidence_matches: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ImportedDocument:
    """Metadata and provenance from a CSV, XLSX, or PDF document."""
    kind: str
    digest_sha256: str
    filename: str
    total_rows: int
    total_columns: int
    warnings: list[str] = field(default_factory=list)
    provenance_map: dict[int, str] = field(default_factory=dict)


@dataclass
class MathRuleConfig:
    """User-configured or preset mathematical validation rule."""
    rule_id: str
    rule_type: str  # "formula", "sum", "percentage", "percentage_change", "constraint", "outlier"
    target_column: Optional[str] = None
    expression: Optional[str] = None  # e.g. "qty * price - discount + tax"
    addend_columns: Optional[list[str]] = None  # e.g. ["item1", "item2", "item3"]
    part_column: Optional[str] = None
    total_column: Optional[str] = None
    old_column: Optional[str] = None
    new_column: Optional[str] = None
    constraint_type: Optional[str] = None  # "non_negative", "positive", "min", "max", "integer_only", "less_than_column"
    constraint_value: Optional[str] = None
    tolerance: str = "0.01"
    decimal_places: int = 2
    rounding_mode: str = "ROUND_HALF_UP"
    severity: str = "High"
    description: Optional[str] = None

