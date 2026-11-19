from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

from cleartrace.models import AuditEvent, RepairProposal, MathFinding, MathRuleConfig
from cleartrace.repair import apply_repair
from cleartrace.timemachine import TimeMachine
from cleartrace.math_engine import inspect_invoice_dataset, inspect_dataset_math
from cleartrace.retrieval import build_session_evidence_index, EvidenceIndex


class StaleRevisionError(Exception):
    """Raised when an approval is attempted against an out-of-date dataset revision."""
    pass


class SessionManager:
    """Manages dataset lifecycle, monotonic revisioning, Time Machine snapshots, undo stack, and audit logging."""

    def __init__(
        self,
        original_df: pd.DataFrame,
        filename: str = "dataset.csv",
        provenance_map: Optional[Dict[int, str]] = None,
        document_format: str = "csv",
        warnings: Optional[List[str]] = None,
    ) -> None:
        self.filename = filename
        self.document_format = document_format
        self.provenance_map = provenance_map or {i: f"{filename}:row {i + 2}" for i in range(len(original_df))}
        self.warnings: List[str] = warnings or []
        self.original_df = original_df.copy()
        self.working_df = original_df.copy()
        self.dataset_revision: int = 1
        self.audit_events: List[AuditEvent] = []
        self._undo_stack: List[Tuple[pd.DataFrame, str, str]] = []  # (prev_df, event_id, reason)
        self.time_machine = TimeMachine(self.working_df, initial_description=f"Loaded {filename}")
        self.math_findings: List[MathFinding] = []
        self.custom_math_rules: List[MathRuleConfig] = []
        self._evidence_index: Optional[EvidenceIndex] = None

        # Record initial ingestion event
        init_event = AuditEvent.create(
            event_id=f"evt-ingest-0",
            rev_before=0,
            rev_after=1,
            actor="system",
            decision="loaded",
            rule_id="initial-load",
            target_columns=list(original_df.columns),
            target_rows=list(range(len(original_df))),
            before_summary="N/A",
            after_summary=f"Loaded {len(original_df)} rows, {len(original_df.columns)} columns from {filename} ({document_format.upper()})",
            reason=f"Uploaded dataset {filename}",
            items_changed=len(original_df),
        )
        self.audit_events.append(init_event)

    def get_math_findings(self, tolerance_val: float = 0.01, df: Optional[pd.DataFrame] = None) -> List[MathFinding]:
        """Inspect working (or explicitly provided) dataset for deterministic mathematical errors."""
        from decimal import Decimal
        target_df = df if df is not None else self.working_df
        findings: List[MathFinding] = []

        # 1. Custom configured math rules
        if getattr(self, "custom_math_rules", None):
            findings.extend(
                inspect_dataset_math(
                    target_df,
                    rules=self.custom_math_rules,
                    source_name=self.filename,
                )
            )

        # 2. Invoice invariant math (if invoice columns are present)
        cols = set(target_df.columns)
        if {"quantity", "unit_price", "recorded_total"}.issubset(cols) or {"qty", "price", "total"}.issubset(cols):
            inv_f = inspect_invoice_dataset(
                target_df,
                tolerance=Decimal(str(tolerance_val)),
                source_name=self.filename,
            )
            existing_ids = {f.id for f in findings}
            findings.extend([f for f in inv_f if f.id not in existing_ids])

        if df is None:
            self.math_findings = findings
        return findings

    def get_evidence_index(self, quality_findings=None) -> EvidenceIndex:
        """Builds or returns a session-isolated EvidenceIndex for RAG retrieval."""
        math_f = self.get_math_findings()
        self._evidence_index = build_session_evidence_index(
            df=self.working_df,
            filename=self.filename,
            provenance_map=self.provenance_map,
            quality_findings=quality_findings,
            math_findings=math_f,
        )
        return self._evidence_index


    def apply_proposal(self, proposal: RepairProposal, expected_revision: Optional[int] = None) -> AuditEvent:
        """Applies an approved repair with revision checking, audit recording, Time Machine snapshot, and undo support."""
        if expected_revision is not None and expected_revision != self.dataset_revision:
            raise StaleRevisionError(
                f"Stale approval rejected: Expected revision {expected_revision}, but current revision is {self.dataset_revision}."
            )

        prev_df = self.working_df.copy()
        new_df, changed_count, detail_msg = apply_repair(prev_df, proposal)

        rev_before = self.dataset_revision
        rev_after = rev_before + 1
        event_id = f"evt-{proposal.rule_id}-{rev_after}"

        event = AuditEvent.create(
            event_id=event_id,
            rev_before=rev_before,
            rev_after=rev_after,
            actor="user",
            decision="approved",
            rule_id=proposal.rule_id,
            target_columns=[proposal.column],
            target_rows=proposal.target_rows,
            before_summary=proposal.before_summary,
            after_summary=proposal.after_summary,
            reason=detail_msg,
            items_changed=changed_count,
        )

        self._undo_stack.append((prev_df, event_id, proposal.rule_id))
        self.working_df = new_df
        self.dataset_revision = rev_after
        self.audit_events.append(event)

        # Record snapshot in Time Machine
        self.time_machine.record_snapshot(
            revision=rev_after,
            df=new_df,
            action=f"REPAIR_{proposal.rule_id.upper()}",
            description=detail_msg,
        )

        return event

    def undo_last_action(self) -> Optional[AuditEvent]:
        """Reverses the last applied action, restoring the previous working DataFrame."""
        if not self._undo_stack:
            return None

        prev_df, undone_event_id, rule_id = self._undo_stack.pop()
        rev_before = self.dataset_revision
        rev_after = rev_before + 1
        event_id = f"evt-undo-{rev_after}"

        event = AuditEvent.create(
            event_id=event_id,
            rev_before=rev_before,
            rev_after=rev_after,
            actor="user",
            decision="undone",
            rule_id=rule_id,
            target_columns=[],
            target_rows=[],
            before_summary="Current state before undo",
            after_summary=f"Reverted to state before event {undone_event_id}",
            reason=f"User triggered undo of event {undone_event_id}",
            items_changed=0,
            undo_of=undone_event_id,
        )

        self.working_df = prev_df
        self.dataset_revision = rev_after
        self.audit_events.append(event)

        self.time_machine.record_snapshot(
            revision=rev_after,
            df=prev_df,
            action="UNDO",
            description=f"Undid event {undone_event_id}",
        )

        return event

    def reset_to_original(self) -> AuditEvent:
        """Resets the working DataFrame back to the immutable original baseline."""
        rev_before = self.dataset_revision
        rev_after = rev_before + 1
        event_id = f"evt-reset-{rev_after}"

        event = AuditEvent.create(
            event_id=event_id,
            rev_before=rev_before,
            rev_after=rev_after,
            actor="user",
            decision="reset",
            rule_id="reset-original",
            target_columns=list(self.original_df.columns),
            target_rows=list(range(len(self.original_df))),
            before_summary=f"Working copy at revision {rev_before}",
            after_summary="Restored to original baseline upload",
            reason="User reset dataset to original immutable upload",
            items_changed=len(self.working_df),
        )

        self.working_df = self.original_df.copy()
        self._undo_stack.clear()
        self.dataset_revision = rev_after
        self.audit_events.append(event)

        self.time_machine.record_snapshot(
            revision=rev_after,
            df=self.working_df,
            action="RESET",
            description="Restored dataset to raw original upload",
        )

        return event

    def restore_to_revision(self, target_revision: int) -> AuditEvent:
        """Restores dataset to any historical snapshot recorded in the Time Machine."""
        snap = self.time_machine.get_snapshot(target_revision)
        if snap is None:
            raise ValueError(f"Revision {target_revision} not found in Time Machine.")

        rev_before = self.dataset_revision
        rev_after = rev_before + 1
        event_id = f"evt-restore-r{target_revision}-{rev_after}"

        event = AuditEvent.create(
            event_id=event_id,
            rev_before=rev_before,
            rev_after=rev_after,
            actor="user",
            decision="restored",
            rule_id="time-machine-restore",
            target_columns=list(snap.frame.columns),
            target_rows=list(range(len(snap.frame))),
            before_summary=f"Working copy at revision {rev_before}",
            after_summary=f"Restored to snapshot of revision {target_revision} ({snap.description})",
            reason=f"Time Machine jump to revision {target_revision}",
            items_changed=len(snap.frame),
            undo_of=f"rev-{target_revision}",
        )

        # Save previous state to undo stack
        self._undo_stack.append((self.working_df.copy(), event_id, "time-machine-restore"))
        self.working_df = snap.frame.copy()
        self.dataset_revision = rev_after
        self.audit_events.append(event)

        self.time_machine.record_snapshot(
            revision=rev_after,
            df=self.working_df,
            action=f"RESTORE_R{target_revision}",
            description=f"Time Machine restored to revision {target_revision}",
        )

        return event
