from datetime import datetime

import pandas as pd

from scripts.profile_data import (
    classify_po_bucket,
    opening_balance_before_first_transaction,
    rank_wp_candidates,
    rank_wp_rows_against_gl,
    summarize_phrase_decisions,
)


def test_classify_po_bucket_distinguishes_wp_debit_unknown_and_missing_codes():
    wp_codes = {"TP01/PO/26010005"}
    debit_codes = {"HLJC/WO/26040003"}

    assert classify_po_bucket(["TP01/PO/26010005"], wp_codes, debit_codes) == "PO ada di WP"
    assert classify_po_bucket(["HLJC/WO/26040003"], wp_codes, debit_codes) == "PO hanya ada di DEBET GL"
    assert classify_po_bucket(["UNKNOWN/PO/26040001"], wp_codes, debit_codes) == "kode PO tidak dikenal"
    assert classify_po_bucket([], wp_codes, debit_codes) == "tanpa kode PO"


def test_rank_wp_candidates_preserves_unit_tokens_and_reports_comparisons():
    working_paper = pd.DataFrame(
        [
            {
                "wp_row": 9,
                "date": datetime(2026, 1, 22),
                "description": "STYLING APARTEMEN THE PARC SM 1132 (2 BEDROOM)",
                "amount": 25_695_900.0,
                "realization_amount": 2_028_300.0,
            },
            {
                "wp_row": 10,
                "date": datetime(2026, 1, 22),
                "description": "STYLING APARTEMEN THE PARC SM 1127 (STUDIO)",
                "amount": 1_583_700.0,
                "realization_amount": 268_000.0,
            },
        ]
    )

    candidates = rank_wp_candidates(
        "PENGEMBALIAN KELEBIHAN DANA UM STYLING APARTEMEN THE PARC SM 1132 (2 BEDROOM) P-SDT/I/070",
        pengajuan_month=1,
        amount=23_667_600.0,
        working_paper=working_paper,
        top_n=2,
    )

    assert [candidate["wp_row"] for candidate in candidates] == [9, 10]
    assert candidates[0]["score"] > candidates[1]["score"]
    assert candidates[0]["application_month_matches"] is True
    assert candidates[0]["amount_matches_amount_or_balance"] is True


def test_rank_wp_rows_against_gl_returns_each_working_paper_row():
    working_paper = pd.DataFrame(
        [
            {"wp_row": 8, "date": datetime(2026, 1, 22), "description": "BAR STOOL SM 1132", "amount": 2_500_000.0},
            {"wp_row": 9, "date": datetime(2026, 1, 22), "description": "PAKET MEETING KIRANA", "amount": 1_750_000.0},
        ]
    )
    gl_rows = pd.DataFrame(
        [
            {
                "gl_row": 15,
                "gl_date": datetime(2026, 4, 2),
                "voucher_no": "ADV/BK/2604/0004",
                "description": "TP01/PO/26010005 BAR STOOL SM 1132",
                "po_codes": ["TP01/PO/26010005"],
                "pengajuan_month": None,
                "txn_type": "SETTLEMENT",
                "credit": 2_500_000.0,
                "debit": 0.0,
            }
        ]
    )

    result = rank_wp_rows_against_gl(working_paper, gl_rows)

    assert result["wp_row"].tolist() == [8, 9]
    assert result.iloc[0]["voucher_no"] == "ADV/BK/2604/0004"


def test_opening_balance_reverses_first_transaction_from_running_balance():
    gl_rows = pd.DataFrame(
        [{"balance": 995_997_385.0, "debit": 2_330_500.0, "credit": 0.0}]
    )

    assert opening_balance_before_first_transaction(gl_rows) == 993_666_885.0


def test_summarize_phrase_decisions_flags_ambiguous_candidates():
    candidates = pd.DataFrame(
        [
            {"gl_row": 3, "rank": 1, "wp_row": 8, "score": 0.72, "application_month_matches": True},
            {"gl_row": 3, "rank": 2, "wp_row": 9, "score": 0.66, "application_month_matches": True},
        ]
    )

    decisions = summarize_phrase_decisions(candidates)

    assert decisions.loc[0, "status"] == "ambiguous"
