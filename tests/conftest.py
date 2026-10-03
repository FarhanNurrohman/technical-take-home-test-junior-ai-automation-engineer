import pytest

import pandas as pd


@pytest.fixture
def sample_workspace_dir(tmp_path):
    return tmp_path


@pytest.fixture
def chat_artifacts():
    result = pd.DataFrame(
        [
            {
                "target_id": "WP-9",
                "section": "WP",
                "description": "STYLING SM 1132 (2 BEDROOM)",
                "amount": 25_695_900,
                "realization_amount": 2_028_300,
                "balance": 23_667_600,
                "status": "PARTIAL",
                "settlement_total": 0,
                "refund_total": 2_028_300,
                "adjustment_total": 0,
                "need_settlement_evidence": True,
            },
            {
                "target_id": "WP-10",
                "section": "WP",
                "description": "STYLING SM 1127 (STUDIO)",
                "amount": 1_583_700,
                "realization_amount": 268_000,
                "balance": 1_315_700,
                "status": "PARTIAL",
                "settlement_total": 0,
                "refund_total": 308_000,
                "adjustment_total": 40_000,
                "need_settlement_evidence": True,
            },
            {
                "target_id": "NEW-FR01/PO/26040004",
                "section": "NEW_ADVANCE",
                "description": "ADVANCE BARU FR01/PO/26040004",
                "amount": 900_000,
                "realization_amount": 0,
                "balance": 900_000,
                "status": "UNSETTLED",
            },
        ]
    )
    return {
        "df_result": result,
        "metrics": {
            "wp": {"total_advance": 27_279_600, "total_realization": 2_296_300, "total_balance": 24_983_300, "item_count": 2},
            "new_advance": {"total_advance": 900_000, "total_realization": 0, "total_balance": 900_000, "item_count": 1},
            "unmatched_count": 1,
            "unmatched_total": 75_000,
            "unmatched_by_reason": {"ambiguous": 1},
            "unsettled_items": [],
        },
        "reconcile_result": {"diff_total": 0, "total_credit_gl": 2_371_300},
        "df_unmatched": pd.DataFrame(
            [{"reason": "ambiguous", "amount": 75_000, "txn_type": "SETTLEMENT", "description": "DATA tidak tepercaya"}]
        ),
    }