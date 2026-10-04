"""Read-only data sources used by the Finance Assistant."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

import pandas as pd

from src.ai_summary import compute_metrics


class DataSource(Protocol):
    """Minimal read-only contract required by the chatbot."""

    def load_flat(self) -> pd.DataFrame: ...

    def load_unmatched(self) -> pd.DataFrame: ...

    def load_meta(self) -> dict[str, Any]: ...

    def freshness(self) -> dict[str, Any]: ...

    def refresh(self) -> None: ...


@dataclass
class ArtifactDataSource:
    """Expose an already-loaded pipeline artifact without network access."""

    artifacts: dict[str, Any]
    _cache_hit: bool = False

    def load_flat(self) -> pd.DataFrame:
        frame = self.artifacts.get("df_result")
        if not isinstance(frame, pd.DataFrame):
            raise ValueError("Artifact chatbot tidak memiliki df_result DataFrame yang valid.")
        result = frame.copy()
        if "saldo" not in result.columns and "balance" in result.columns:
            result["saldo"] = result["balance"]
        return result

    def load_unmatched(self) -> pd.DataFrame:
        frame = self.artifacts.get("df_unmatched", pd.DataFrame())
        if not isinstance(frame, pd.DataFrame):
            raise ValueError("Artifact chatbot tidak memiliki df_unmatched DataFrame yang valid.")
        return frame.copy()

    def load_meta(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "generated_at": self.artifacts.get("generated_at"),
            "period": self.artifacts.get("metrics", {}).get("period", "April 2026"),
            "reconcile_ok": self.artifacts.get("metrics", {}).get("reconcile_ok", False),
            "reconcile_diff": self.artifacts.get("metrics", {}).get("reconcile_diff", 0),
        }

    def freshness(self) -> dict[str, Any]:
        return {
            "generated_at": self.load_meta().get("generated_at"),
            "cache_hit": self._cache_hit,
            "stale": False,
        }

    def refresh(self) -> None:
        self._cache_hit = False


class DemoDataSource(ArtifactDataSource):
    """Synthetic fixture source that never contacts Google Sheets."""

    def __init__(self) -> None:
        result = pd.DataFrame(
            [
                {
                    "target_id": "WP-DEMO-1",
                    "section": "WP",
                    "description": "STYLING SM 1127 (STUDIO)",
                    "amount": 1_583_700,
                    "realization_amount": 268_000,
                    "balance": 1_315_700,
                    "status": "PARTIAL",
                    "settlement_total": 0,
                    "refund_total": 268_000,
                    "need_settlement_evidence": True,
                },
                {
                    "target_id": "WP-DEMO-2",
                    "section": "WP",
                    "description": "PBB JV 2 SUMMARECON",
                    "amount": 500_000,
                    "realization_amount": 0,
                    "balance": 500_000,
                    "status": "UNSETTLED",
                    "settlement_total": 0,
                    "refund_total": 0,
                    "need_settlement_evidence": False,
                },
                {
                    "target_id": "NEW-DEMO-1",
                    "section": "NEW_ADVANCE",
                    "description": "ADVANCE BARU APRIL",
                    "amount": 900_000,
                    "realization_amount": 0,
                    "balance": 900_000,
                    "status": "UNSETTLED",
                    "settlement_total": 0,
                    "refund_total": 0,
                    "need_settlement_evidence": False,
                },
            ]
        )
        unmatched = pd.DataFrame([{"reason": "ambiguous", "amount": 75_000, "txn_type": "SETTLEMENT"}])
        metrics = compute_metrics(result, {"diff_total": 0, "reconcile_ok": True}, unmatched)
        super().__init__(
            {
                "df_result": result,
                "df_unmatched": unmatched,
                "metrics": metrics,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
