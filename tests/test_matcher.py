import pandas as pd

from src.matcher import aggregate_realizations, build_targets, match_gl_to_targets, reconcile


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
