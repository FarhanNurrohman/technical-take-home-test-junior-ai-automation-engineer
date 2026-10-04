from __future__ import annotations

import pandas as pd
import pytest

import main


def test_dry_run_pipeline_writes_excel_and_json_without_external_calls(tmp_path, mocker):
    gl = pd.DataFrame(
        [
            {
                "gl_row": 10,
                "gl_date": pd.Timestamp("2026-04-17"),
                "voucher_no": "PMT2/BM/2604/0007",
                "description": "PENGEMBALIAN UM STYLING SM 1132 (2 BEDROOM) P-SDT/I/070",
                "debit": 0,
                "credit": 2_028_300,
                "balance": 100_000,
            },
            {
                "gl_row": 11,
                "gl_date": pd.Timestamp("2026-04-18"),
                "voucher_no": "ADV/BK/2604/0014",
                "description": "ADVANCE FR01/PO/26040004",
                "debit": 900_000,
                "credit": 0,
                "balance": 1_000_000,
            },
        ]
    )
    wp = pd.DataFrame(
        [
            {
                "wp_row": 9,
                "date": pd.Timestamp("2026-01-10"),
                "voucher_no": "PMT2/BK/2601/0009",
                "description": "STYLING SM 1132 (2 BEDROOM) P-SDT/I/070",
                "amount": 25_695_900,
            }
        ]
    )
    mocker.patch.object(main, "load_gl", return_value=gl)
    mocker.patch.object(main, "load_working_paper", return_value=(wp, {"header_row": 6, "first_row": 8, "last_row": 8}))
    gemini = mocker.patch.object(main, "generate_executive_summary")
    sheets = mocker.patch.object(main, "export_to_sheets")

    report = main.run_pipeline(output_dir=tmp_path, dry_run=True)

    assert report["reconcile_result"]["diff_total"] == 0
    assert report["df_result"].loc[0, "realization_amount"] == pytest.approx(2_028_300)
    assert (tmp_path / "result.xlsx").is_file()
    assert (tmp_path / "result.json").is_file()
    assert (tmp_path / "unmatched.json").is_file()
    gemini.assert_not_called()
    sheets.assert_not_called()


def test_pipeline_stops_before_export_when_reconciliation_fails(tmp_path, mocker):
    mocker.patch.object(main, "load_gl", return_value=pd.DataFrame(columns=["gl_row", "gl_date", "voucher_no", "description", "debit", "credit", "balance"]))
    mocker.patch.object(main, "load_working_paper", return_value=(pd.DataFrame(columns=["wp_row", "date", "voucher_no", "description", "amount"]), {}))
    mocker.patch.object(main, "reconcile", side_effect=ValueError("Reconciliation failed"))

    with pytest.raises(ValueError, match="Reconciliation failed"):
        main.run_pipeline(output_dir=tmp_path, dry_run=True)

    assert not (tmp_path / "result.xlsx").exists()


def test_main_dry_run_returns_nonzero_on_reconciliation_failure(mocker):
    mocker.patch("sys.argv", ["main.py", "--dry-run"])
    mocker.patch.object(main, "run_pipeline", side_effect=ValueError("Reconciliation failed"))

    assert main.main() == 1


def test_main_launches_chat_after_successful_pipeline(mocker):
    pipeline_result = {
        "metrics": {
            "wp": {"total_advance": 0, "total_realization": 0},
            "unmatched_count": 0,
            "unmatched_total": 0,
        },
        "reconcile_result": {"diff_total": 0},
    }
    mocker.patch("sys.argv", ["main.py", "--dry-run", "--no-ai"])
    mocker.patch.object(main, "run_pipeline", return_value=pipeline_result)
    launch_chat = mocker.patch.object(main, "launch_chat")

    assert main.main() == 0

    launch_chat.assert_called_once_with(
        pipeline_result,
        use_ai=False,
        data_status="Data pipeline settlement (snapshot saat pipeline selesai)",
    )