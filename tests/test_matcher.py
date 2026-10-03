import pandas as pd

from src.matcher import (
    aggregate_realizations,
    build_targets,
    match_gl_to_targets,
    reconcile,
    suggest_settlement_candidates,
    summarize_sections,
)


def test_build_targets_and_aggregate_realizations_for_refund_only_case():
    wp = pd.DataFrame([
        {
            "wp_row": 8,
            "date": "2026-01-22",
            "voucher_no": "PMT2/BK/2604/0001",
            "description": "STYLING APARTEMEN THE PARC SM 1132 (2 BEDROOM)",
            "amount": 25_695_900,
            "realization_date": None,
            "realization_voucher_no": None,
            "realization_amount": None,
            "balance": None,
            "notes": None,
        }
    ])
    gl = pd.DataFrame([
        {
            "gl_row": 1,
            "gl_date": "2026-04-17",
            "voucher_no": "PMT2/BM/2604/0007",
            "description": "PENGEMBALIAN KELEBIHAN DANA UM STYLING APARTEMEN THE PARC SM 1132 (2 BEDROOM) (P-SDT/I/070)",
            "debit": 0,
            "credit": 2_028_300,
            "txn_type": "REFUND",
            "po_codes": [],
            "pengajuan_code": "P-SDT/I/070",
            "pengajuan_month": 1,
        },
        {
            "gl_row": 2,
            "gl_date": "2026-04-27",
            "voucher_no": "KK/HO/2604/0006",
            "description": "PENGEMBALIAN KELEBIHAN DANA UM STYLING APARTEMEN THE PARC SM 1127 (STUDIO) (P-SDT/I/071)",
            "debit": 40_000,
            "credit": 0,
            "txn_type": "ADJUSTMENT",
            "po_codes": [],
            "pengajuan_code": "P-SDT/I/071",
            "pengajuan_month": 1,
        },
    ])

    targets, _ = build_targets(wp, gl)
    matches, unmatched = match_gl_to_targets(gl, targets)
    result = aggregate_realizations(targets, matches, gl)

    assert list(targets["target_id"]) == ["WP-8"]
    assert result.loc[0, "status"] == "PARTIAL"
    assert result.loc[0, "need_settlement_evidence"]
    assert result.loc[0, "realization_amount"] == 2_028_300
    assert result.loc[0, "balance"] == 23_667_600

    summary = reconcile(gl, matches, unmatched, targets)
    assert summary["diff_total"] == 0


def test_phrase_matching_filters_candidates_by_advance_month():
    targets = pd.DataFrame(
        [
            {
                "target_id": "WP-1",
                "target_type": "WP",
                "date": "2026-01-22",
                "description": "UM SHOW UNIT THE PARC BULAN MARET 2026",
                "amount": 2_600_000,
                "po_codes": [],
                "pengajuan_code": None,
                "pengajuan_month": None,
            },
            {
                "target_id": "WP-2",
                "target_type": "WP",
                "date": "2026-04-02",
                "description": "UM ACARA SHOW UNIT THE PARC BULAN MARET 2026",
                "amount": 2_600_000,
                "po_codes": [],
                "pengajuan_code": None,
                "pengajuan_month": None,
            },
        ]
    )
    gl = pd.DataFrame(
        [
            {
                "gl_row": 1,
                "voucher_no": "PMT2/BM/2604/0001",
                "description": "PENGEMBALIAN UM SHOW UNIT THE PARC BULAN MARET 2026 (P-SDT/IV/005)",
                "txn_type": "REFUND",
                "po_codes": [],
                "pengajuan_code": "P-SDT/IV/005",
                "pengajuan_month": 4,
            }
        ]
    )

    matches, unmatched = match_gl_to_targets(gl, targets)

    assert matches["target_id"].tolist() == ["WP-2"]
    assert unmatched.empty


def test_phrase_matching_finds_labeled_dropbox_settlement():
    targets = pd.DataFrame(
        [
            {
                "target_id": "WP-21",
                "target_type": "WP",
                "date": "2026-03-14",
                "description": "ADVANCE PEMBAYARAN KARTU KREDIT BCA UNTUK TAGIHAN DROPBOX PERIODE 11/3/2026 - 11/3/2027",
                "amount": 60_000_000,
                "po_codes": [],
                "pengajuan_code": None,
                "pengajuan_month": None,
            }
        ]
    )
    gl = pd.DataFrame(
        [
            {
                "gl_row": 1,
                "voucher_no": "BCA2/BK/2604/0026",
                "description": "PELUNASAN TAGIHAN DROPBOX PERIODE 11/3/2026 - 11/3/2027 (USD 3.996 X RP 17.178,87) (BCA2/III/052)",
                "txn_type": "SETTLEMENT",
                "po_codes": [],
                "pengajuan_code": "BCA2/III/052",
                "pengajuan_month": 3,
            }
        ]
    )

    matches, unmatched = match_gl_to_targets(gl, targets)

    assert matches["target_id"].tolist() == ["WP-21"]
    assert unmatched.empty


def test_unmatched_rows_retain_gl_date_and_amount_for_audit_export():
    gl = pd.DataFrame(
        [
            {
                "gl_row": 31,
                "gl_date": "2026-04-12",
                "voucher_no": "PMT2/BM/2604/0031",
                "description": "SETTLEMENT UNKNOWN/PO/26040001",
                "debit": 0,
                "credit": 125_000,
                "txn_type": "SETTLEMENT",
                "po_codes": ["UNKNOWN/PO/26040001"],
                "pengajuan_code": None,
                "pengajuan_month": None,
            }
        ]
    )
    targets = pd.DataFrame(columns=["target_id", "description", "po_codes", "pengajuan_code", "pengajuan_month"])

    matches, unmatched = match_gl_to_targets(gl, targets)

    assert matches.empty
    assert unmatched.loc[0, "gl_date"] == "2026-04-12"
    assert unmatched.loc[0, "credit"] == 125_000
    assert unmatched.loc[0, "debit"] == 0


def test_build_targets_groups_new_advances_and_keeps_uncoded_advances_separate():
    gl = pd.DataFrame(
        [
            {"gl_row": 1, "gl_date": "2026-04-02", "voucher_no": "ADV1", "description": "ADVANCE FR01/PO/26040004", "debit": 40, "credit": 0, "txn_type": "NEW_ADVANCE", "po_codes": ["FR01/PO/26040004"]},
            {"gl_row": 2, "gl_date": "2026-04-01", "voucher_no": "ADV2", "description": "ADVANCE FR01/PO/26040004 P-SDT/IV/005", "debit": 60, "credit": 0, "txn_type": "NEW_ADVANCE", "po_codes": ["FR01/PO/26040004"]},
            {"gl_row": 3, "gl_date": "2026-04-03", "voucher_no": "ADV3", "description": "ADVANCE NON PO", "debit": 25, "credit": 0, "txn_type": "NEW_ADVANCE", "po_codes": []},
            {"gl_row": 4, "gl_date": "2026-04-03", "voucher_no": "D1", "description": "Debit existing PO", "debit": 7, "credit": 0, "txn_type": "UNCLASSIFIED_DEBIT", "po_codes": []},
        ]
    )

    targets, debit_exceptions = build_targets(pd.DataFrame(), gl)

    grouped = targets.set_index("target_id").loc["NEW-FR01/PO/26040004"]
    assert grouped["amount"] == 100
    assert grouped["voucher_no"] == "ADV1, ADV2"
    assert grouped["date"] == "2026-04-01"
    assert targets.set_index("target_id").loc["NEW-3", "amount"] == 25
    assert debit_exceptions["gl_row"].tolist() == [4]


def test_match_rejects_pengajuan_conflict_and_ambiguous_phrases():
    targets = pd.DataFrame(
        [
            {"target_id": "WP-1", "description": "STYLING SM 1127 STUDIO", "date": "2026-01-01", "po_codes": [], "pengajuan_code": "P-SDT/I/071"},
            {"target_id": "WP-2", "description": "STYLING SM 1127 STUDIO", "date": "2026-01-02", "po_codes": [], "pengajuan_code": "P-SDT/I/071"},
            {"target_id": "WP-3", "description": "PBB JV 2 SUMMARECON", "date": "2026-01-03", "po_codes": [], "pengajuan_code": None},
            {"target_id": "WP-4", "description": "PBB JV 2 SUMMARECON", "date": "2026-01-04", "po_codes": [], "pengajuan_code": None},
        ]
    )
    gl = pd.DataFrame(
        [
            {"gl_row": 1, "voucher_no": "R1", "description": "REFUND P-SDT/I/071", "txn_type": "REFUND", "po_codes": [], "pengajuan_code": "P-SDT/I/071", "pengajuan_month": 1},
            {"gl_row": 2, "voucher_no": "S1", "description": "PBB JV 2 SUMMARECON", "txn_type": "SETTLEMENT", "po_codes": [], "pengajuan_code": None, "pengajuan_month": None},
        ]
    )

    matches, unmatched = match_gl_to_targets(gl, targets)

    assert matches.empty
    assert unmatched.set_index("gl_row")["reason"].to_dict() == {1: "pengajuan_conflict", 2: "ambiguous"}


def test_match_phrase_with_month_mismatch_and_skip_noneligible_rows():
    targets = pd.DataFrame(
        [{"target_id": "WP-1", "description": "PBB JV 2", "date": "2026-03-02", "po_codes": [], "pengajuan_code": None}]
    )
    gl = pd.DataFrame(
        [
            {"gl_row": 1, "voucher_no": "M1", "description": "PBB JV 2", "txn_type": "SETTLEMENT", "po_codes": [], "pengajuan_code": "P-SDT/IV/005", "pengajuan_month": 4},
            {"gl_row": 2, "voucher_no": "D1", "description": "debit", "txn_type": "UNCLASSIFIED_DEBIT", "po_codes": [], "pengajuan_code": None, "pengajuan_month": None},
        ]
    )

    matches, unmatched = match_gl_to_targets(gl, targets)

    assert matches.empty
    assert unmatched.loc[0, "reason"] == "month_mismatch"
    assert unmatched["gl_row"].tolist() == [1]


def test_empty_aggregation_and_section_summary_are_well_shaped():
    targets = pd.DataFrame(columns=["target_id", "target_type", "amount"])
    result = aggregate_realizations(targets, pd.DataFrame(), pd.DataFrame())

    assert result.empty
    assert summarize_sections(result).columns.tolist() == ["section", "rows", "amount_total", "realization_total", "balance_total"]
    assert reconcile(pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame())["diff_total"] == 0


def test_suggest_settlement_candidates_uses_remaining_amount_or_unit_code():
    result = pd.DataFrame(
        [{"target_id": "WP-9", "description": "STYLING SM 1132", "amount": 100, "realization_amount": 20, "balance": 80, "status": "PARTIAL", "need_settlement_evidence": True}]
    )
    gl = pd.DataFrame(
        [
            {"gl_row": 10, "voucher_no": "V10", "description": "UNKNOWN", "credit": 80},
            {"gl_row": 11, "voucher_no": "V11", "description": "SETTLEMENT STYLING SM 1132", "credit": 5},
            {"gl_row": 12, "voucher_no": "V12", "description": "UNRELATED", "credit": 7},
        ]
    )
    unmatched = pd.DataFrame([{"gl_row": 10}, {"gl_row": 11}, {"gl_row": 12}])

    suggestions = suggest_settlement_candidates(result, gl, unmatched)

    assert suggestions["gl_row"].tolist() == [10, 11]
    assert suggestions["alasan"].tolist() == ["amount matches remaining balance", "same unit code"]
