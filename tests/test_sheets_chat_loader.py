from __future__ import annotations

from unittest.mock import Mock

import pytest

from src.chat_assistant import fallback_answer
from src.sheets_chat_loader import load_chat_artifacts_from_sheets
from src.sheets_exporter import create_sheets_client


@pytest.fixture
def sheet_values():
    working_paper = [
        ["PT. SETIAWAN DWI TUNGGAL"],
        [""],
        [""],
        [""],
        [""],
        ["Date", "Voucher No", "Description", "Amount", "Realization", "No. Voucher", "Amount", "Saldo", "Description (catatan)", "Status", "Flag", "Target ID"],
        ["", "", "", "", "Date", "No. Voucher", "Amount", "", "", "", "", ""],
        ["A. ADVANCE AWAL (Working Paper)"],
        ["2026-01-01", "PRIVATE-WP-VOUCHER", "STYLING SM 1127 (STUDIO)", "1.583.700", "2026-04-27", "PRIVATE-GL-VOUCHER", "268.000", "1.315.700", "", "PARTIAL", "BUTUH BUKTI REALISASI", "WP-8"],
        ["Subtotal A"],
        [""],
        ["B. ADVANCE BARU APRIL 2026 (dari GL DEBET)"],
        ["2026-04-01", "PRIVATE-WP-VOUCHER-2", "NEW FR01/PO/26040004", "900.000", "", "", "0", "900.000", "", "UNSETTLED", "", "NEW-FR01/PO/26040004"],
    ]
    unmatched = [
        ["KREDIT/ADJUSTMENT TIDAK TER-MATCH"],
        ["GL row", "Tanggal", "No Jurnal", "Txn Type", "Nominal", "Alasan", "Deskripsi"],
        ["47", "2026-04-17", "PRIVATE-JOURNAL", "SETTLEMENT", "75.000", "ambiguous", "PRIVATE RAW DESCRIPTION"],
        ["Total nominal KREDIT/ADJUSTMENT unmatched", "", "", "", "75.000", "", ""],
        [""],
        ["DEBET PERLU DICEK"],
    ]
    dashboard = [["Dashboard Advance Settlement April 2026"], [""], ["Rekonsiliasi", "Selisih = 0"]]
    return {
        "Working_Paper_Result": working_paper,
        "Dashboard": dashboard,
        "Unmatched_GL": unmatched,
    }


def test_loader_maps_spreadsheet_values_and_redacts_gl_identifiers(sheet_values, mocker):
    worksheets = {title: Mock() for title in sheet_values}
    for title, worksheet in worksheets.items():
        worksheet.get_all_values.return_value = sheet_values[title]
    spreadsheet = Mock()
    spreadsheet.worksheet.side_effect = worksheets.__getitem__
    client = Mock()
    client.open_by_key.return_value = spreadsheet

    artifacts = load_chat_artifacts_from_sheets(client=client, spreadsheet_key="sheet-key")

    assert artifacts["df_result"].loc[0, "realization_amount"] == 268_000
    assert artifacts["df_result"].loc[0, "balance"] == 1_315_700
    assert artifacts["metrics"]["wp"]["total_advance"] == 1_583_700
    assert artifacts["metrics"]["new_advance"]["total_advance"] == 900_000
    assert artifacts["metrics"]["unmatched_total"] == 75_000
    assert artifacts["reconcile_result"]["reconcile_ok"] is True
    assert "PRIVATE-JOURNAL" not in str(artifacts)
    assert "PRIVATE RAW DESCRIPTION" not in str(artifacts)
    assert "PRIVATE-GL-VOUCHER" not in str(artifacts)
    summary = fallback_answer("Buat ringkasan posisi settlement", artifacts)
    assert "STYLING SM 1127 (STUDIO)" in summary
    assert "Rp 1.315.700" in summary
    assert "Rp 75.000" in summary
    assert "Sumber: get_summary" in summary
    client.open_by_key.assert_called_once_with("sheet-key")


def test_loader_requires_spreadsheet_key_before_authentication(mocker):
    create_client = mocker.patch("src.sheets_chat_loader.create_sheets_client")

    with pytest.raises(ValueError, match="SPREADSHEET_KEY"):
        load_chat_artifacts_from_sheets(spreadsheet_key="")

    create_client.assert_not_called()


def test_loader_rejects_missing_reconciliation_status(sheet_values, mocker):
    sheet_values["Dashboard"] = [["Dashboard"], ["No status"]]
    worksheets = {title: Mock() for title in sheet_values}
    for title, worksheet in worksheets.items():
        worksheet.get_all_values.return_value = sheet_values[title]
    spreadsheet = Mock()
    spreadsheet.worksheet.side_effect = worksheets.__getitem__
    client = Mock()
    client.open_by_key.return_value = spreadsheet

    with pytest.raises(ValueError, match="Rekonsiliasi"):
        load_chat_artifacts_from_sheets(client=client, spreadsheet_key="sheet-key")


def test_loader_ignores_empty_unmatched_placeholder(sheet_values, mocker):
    sheet_values["Unmatched_GL"] = [
        ["KREDIT/ADJUSTMENT TIDAK TER-MATCH"],
        ["GL row", "Tanggal", "No Jurnal", "Txn Type", "Nominal", "Alasan", "Deskripsi"],
        ["Semua transaksi KREDIT ter-match"],
        ["Total nominal KREDIT/ADJUSTMENT unmatched", "", "", "", "0", "", ""],
        [""],
        ["DEBET PERLU DICEK"],
    ]
    worksheets = {title: Mock() for title in sheet_values}
    for title, worksheet in worksheets.items():
        worksheet.get_all_values.return_value = sheet_values[title]
    spreadsheet = Mock()
    spreadsheet.worksheet.side_effect = worksheets.__getitem__
    client = Mock()
    client.open_by_key.return_value = spreadsheet

    artifacts = load_chat_artifacts_from_sheets(client=client, spreadsheet_key="sheet-key")

    assert artifacts["df_unmatched"].empty
    assert artifacts["metrics"]["unmatched_count"] == 0
    assert artifacts["metrics"]["unmatched_total"] == 0


def test_chat_sheets_client_uses_read_only_scope(tmp_path, mocker):
    credential_file = tmp_path / "service-account.json"
    credential_file.write_text('{"client_email":"synthetic@example.test"}', encoding="utf-8")
    mocker.patch("src.sheets_exporter.config.GOOGLE_SHEETS_CRED", str(credential_file))
    credentials = mocker.patch("google.oauth2.service_account.Credentials.from_service_account_file", return_value=object())
    gspread = mocker.patch("gspread.authorize", return_value=object())

    client = create_sheets_client(read_only=True)

    assert client is gspread.return_value
    assert credentials.call_args.kwargs["scopes"] == ["https://www.googleapis.com/auth/spreadsheets.readonly"]
