from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from src.loaders import check_gl_balance_integrity, parse_gl_frame, parse_wp_frame
from src.parsing import (
    classify_gl_rows,
    extract_pengajuan,
    extract_po_codes,
    parse_amount,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1.250.000,50", 1_250_000.50),
        ("1,250,000.50", 1_250_000.50),
        ("2,330,500.00", 2_330_500.00),
        ("Rp 1.000.000", 1_000_000.00),
        ("(1.000)", -1_000.00),
        (None, 0.0),
        (float("nan"), 0.0),
        ("", 0.0),
        ("-", 0.0),
    ],
)
def test_parse_amount_supports_financial_formats(value, expected):
    assert parse_amount(value) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("TP01/PO/26010005", ["TP01/PO/26010005"]),
        ("REVISI PO FR01/PO/26030017 dan HLJC/WO/26040003", [
            "FR01/PO/26030017",
            "HLJC/WO/26040003",
        ]),
        ("hljc/wo/26040003", ["HLJC/WO/26040003"]),
        ("tanpa kode", []),
        (float("nan"), []),
    ],
)
def test_extract_po_codes_returns_all_codes_uppercase(text, expected):
    assert extract_po_codes(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("P-SDT/I/070", ("P-SDT/I/070", 1)),
        ("BCA2/III/052", ("BCA2/III/052", 3)),
        ("P-SDT/IV/005", ("P-SDT/IV/005", 4)),
        ("PMT2/BM/2604/0007", (None, None)),
        ("KK/HO/2604/0006", (None, None)),
        (float("nan"), (None, None)),
    ],
)
def test_extract_pengajuan_uses_roman_month_only(text, expected):
    assert extract_pengajuan(text) == expected


def test_classify_gl_rows_uses_amount_columns_before_description():
    gl_rows = pd.DataFrame(
        [
            {"voucher_no": "PMT2/BM/2604/0007", "description": "PENGEMBALIAN UM P-SDT/I/070", "debit": 0, "credit": 2_028_300},
            {"voucher_no": "PMT2/BM/2604/0008", "description": "PENGEMBALIAN UM P-SDT/I/071", "debit": 0, "credit": 308_000},
            {"voucher_no": "KK/HO/2604/0006", "description": "PENGEMBALIAN UM P-SDT/I/071", "debit": 40_000, "credit": 0},
            {"voucher_no": "ADV/BK/2604/0014", "description": "UNKNOWN/PO/26040001", "debit": 50_000, "credit": 0},
            {"voucher_no": "PMT2/BK/2604/0009", "description": "TP01/PO/26010005", "debit": 20_000, "credit": 0},
        ]
    )

    result = classify_gl_rows(gl_rows, {"TP01/PO/26010005"})

    assert result["txn_type"].tolist() == [
        "REFUND",
        "REFUND",
        "ADJUSTMENT",
        "NEW_ADVANCE",
        "UNCLASSIFIED_DEBIT",
    ]
    assert result.loc[2, "pengajuan_month"] == 1


def test_parse_gl_frame_keeps_transactions_in_file_order_across_blank_rows():
    raw = pd.DataFrame(
        [
            ["TANGGAL", "NO JURNAL", "DESKRIPSI", "DEBET-IDR", "KREDIT-IDR", "SALDO-IDR"],
            [datetime(2026, 4, 1), "ADV/BK/2604/0001", "Advance A", "2,330,500.00", "-", "10,000"],
            [None, None, None, None, None, None],
            [datetime(2026, 4, 2), "PMT2/BM/2604/0001", "PENGEMBALIAN", "-", "308,000.00", "-"],
        ]
    )

    result = parse_gl_frame(raw)

    assert result["gl_row"].tolist() == [2, 4]
    assert result["voucher_no"].tolist() == ["ADV/BK/2604/0001", "PMT2/BM/2604/0001"]
    assert result["debit"].tolist() == [2_330_500.0, 0.0]
    assert result["credit"].tolist() == [0.0, 308_000.0]


def test_parse_wp_frame_detects_header_subheader_and_data_range():
    raw = pd.DataFrame(
        [
            ["PT. SETIAWAN DWI TUNGGAL"],
            ["Uang Muka"],
            ["=#REF!"],
            ["Account"],
            [],
            ["Date", "Voucher No", "Description", "Amount", "Realization", None, None, "Saldo", "Description"],
            [None, None, None, None, "Date", "No. Voucher", "Amount", None, None],
            [datetime(2026, 1, 22), "PMT2/BK/2601/0062", "TP01/PO/26010005", 2_500_000, None, None, None, "=D8-G8", None],
            [None, None, None, None, None, None, None, None, None],
        ]
    )

    result, meta = parse_wp_frame(raw)

    assert meta == {"header_row": 6, "first_row": 8, "last_row": 8}
    assert result["wp_row"].tolist() == [8]
    assert result.loc[0, "amount"] == 2_500_000.0
    assert result.loc[0, "balance"] == "=D8-G8"


def test_check_gl_balance_integrity_uses_previous_file_row():
    gl_rows = pd.DataFrame(
        [
            {"gl_row": 7, "debit": 952_147_790.0, "credit": 0.0, "balance": 952_147_790.0},
            {"gl_row": 8, "debit": 0.0, "credit": 308_000.0, "balance": 951_839_790.0},
            {"gl_row": 9, "debit": 100.0, "credit": 0.0, "balance": 951_839_900.0},
        ]
    )

    result = check_gl_balance_integrity(gl_rows)

    assert result["gl_row"].tolist() == [9]


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
GL_PATH = DATA_DIR / "GL - Advances Other - April 2026.xls"
WP_PATH = DATA_DIR / "Working Paper Advances and Prepayment-Soal.xlsx"


@pytest.mark.skipif(not GL_PATH.exists() or not WP_PATH.exists(), reason="source workbooks unavailable")
def test_original_workbooks_load_without_missing_amounts():
    from src.loaders import load_gl, load_working_paper

    gl = load_gl(GL_PATH)
    wp, meta = load_working_paper(WP_PATH)

    assert not gl.empty
    assert not wp.empty
    assert gl[["debit", "credit"]].notna().all().all()
    assert wp["amount"].notna().all()
    assert meta["first_row"] == 8