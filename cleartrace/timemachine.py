"""ClearTrace — Dataset Time Machine.

Maintains immutable revision snapshots, generates diffs across arbitrary revisions, and powers snapshot restoration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import pandas as pd

from cleartrace.passport import compute_df_sha256


@dataclass
class RevisionSnapshot:
    revision: int
    timestamp_utc: str
    action: str
    description: str
    row_count: int
    col_count: int
    content_hash: str
    frame: pd.DataFrame


@dataclass
class SnapshotComparison:
    from_revision: int
    to_revision: int
    rows_before: int
    rows_after: int
    net_row_change: int
    columns_changed: List[str]
    sample_diffs: List[Dict[str, str]]


class TimeMachine:
    """Manages immutable point-in-time snapshots of the dataset across revisions."""

    def __init__(self, initial_df: pd.DataFrame, initial_description: str = "Initial Upload") -> None:
        self.snapshots: Dict[int, RevisionSnapshot] = {}
        self.record_snapshot(1, initial_df, "INGEST", initial_description)

    def record_snapshot(self, revision: int, df: pd.DataFrame, action: str, description: str) -> RevisionSnapshot:
        """Captures an immutable snapshot of the dataset at a given revision."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        snap = RevisionSnapshot(
            revision=revision,
            timestamp_utc=now_str,
            action=action,
            description=description,
            row_count=len(df),
            col_count=len(df.columns),
            content_hash=compute_df_sha256(df)[:12],
            frame=df.copy(),
        )
        self.snapshots[revision] = snap
        return snap

    def get_snapshot(self, revision: int) -> Optional[RevisionSnapshot]:
        return self.snapshots.get(revision)

    def list_timeline(self) -> List[Dict[str, object]]:
        """Returns ordered timeline metadata for all recorded snapshots."""
        timeline = []
        for rev in sorted(self.snapshots.keys()):
            s = self.snapshots[rev]
            timeline.append({
                "revision": s.revision,
                "timestamp_utc": s.timestamp_utc,
                "action": s.action,
                "description": s.description,
                "row_count": s.row_count,
                "col_count": s.col_count,
                "hash": s.content_hash,
            })
        return timeline

    def compare_revisions(self, rev_from: int, rev_to: int) -> Optional[SnapshotComparison]:
        """Calculates a cell-level and row-level diff between two revisions."""
        snap_a = self.snapshots.get(rev_from)
        snap_b = self.snapshots.get(rev_to)
        if snap_a is None or snap_b is None:
            return None

        df_a = snap_a.frame
        df_b = snap_b.frame

        row_delta = len(df_b) - len(df_a)
        changed_cols = []
        diffs = []

        common_cols = [c for c in df_a.columns if c in df_b.columns]
        min_rows = min(len(df_a), len(df_b))

        for col in common_cols:
            col_diff = False
            for i in range(min_rows):
                val_a = str(df_a.iloc[i][col])
                val_b = str(df_b.iloc[i][col])
                if val_a != val_b:
                    col_diff = True
                    if len(diffs) < 10:
                        diffs.append({
                            "row": str(i + 1),
                            "column": str(col),
                            "before": val_a,
                            "after": val_b,
                        })
            if col_diff:
                changed_cols.append(col)

        return SnapshotComparison(
            from_revision=rev_from,
            to_revision=rev_to,
            rows_before=len(df_a),
            rows_after=len(df_b),
            net_row_change=row_delta,
            columns_changed=changed_cols,
            sample_diffs=diffs,
        )
