"""Load sanitized settlement report data from the configured Google Sheets workbook."""

from __future__ import annotations

import logging
import re
from typing import Any

import pandas as pd

from src import config
from src.ai_summary import compute_metrics
from src.parsing import parse_amount
from src.sheets_exporter import create_sheets_client

logger = logging.getLogger(__name__)
_RESULT_COLUMNS = (
    "target_id",
    "section",
    "description",
    "amount",
    "realization_amount",
    "balance",
    "status",
    "need_settlement_evidence",
    "settlement_total",
)


def _cell(row: list[str], index: int) -> str:
    return row[index].strip() if index < len(row) else ""


def _money(value: str, location: str) -> float:
    try:
        return parse_amount(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Nilai nominal tidak valid di Google Sheets ({location}): {value!r}.") from error


def _read_sheet(spreadsheet: Any, title: str) -> list[list[str]]:
    try:
        values = spreadsheet.worksheet(title).get_all_values()
    except Exception as error:
        logger.exception("Unable to read Google Sheets tab %s", title)
        raise RuntimeError(f"Gagal membaca tab Google Sheets {title!r}; pastikan tab pipeline tersedia dan akses baca diberikan.") from error
    if not isinstance(values, list):
        raise ValueError(f"Format tab Google Sheets {title!r} tidak valid.")
    return values


def _result_rows(values: list[list[str]]) -> list[dict[str, Any]]:
    if not any("Target ID" in row for row in values[:10]):
        raise ValueError("Header 'Target ID' tidak ditemukan pada tab Working_Paper_Result.")
    section: str | None = None
    records: list[dict[str, Any]] = []
    for row_number, row in enumerate(values, start=1):
        first = _cell(row, 0)
        if first.startswith("A. ADVANCE AWAL"):
            section = "WP"
            continue
        if first.startswith("B. ADVANCE BARU"):
            section = "NEW_ADVANCE"
            continue
        target_id = _cell(row, 11)
        if not section or not target_id:
            continue
        description = _cell(row, 2)
        amount = _money(_cell(row, 3), f"Working_Paper_Result!D{row_number}")
        realized = _money(_cell(row, 6), f"Working_Paper_Result!G{row_number}")
        balance = _money(_cell(row, 7), f"Working_Paper_Result!H{row_number}")
        flag = _cell(row, 10).upper()
        status = _cell(row, 9).upper()
        need_evidence = "BUTUH BUKTI REALISASI" in flag
        records.append(
            {
                "target_id": target_id,
                "section": section,
                "description": description,
                "amount": amount,
                "realization_amount": realized,
                "balance": balance,
                "status": status,
                "need_settlement_evidence": need_evidence,
                "settlement_total": realized if status == "PARTIAL" and not need_evidence else 0.0,
            }
        )
    if not records:
        raise ValueError("Tidak ada baris target di tab Working_Paper_Result; jalankan pipeline dan periksa format sheet.")
    return records


def _unmatched_rows(values: list[list[str]]) -> list[dict[str, Any]]:
    if len(values) < 2 or "No Jurnal" not in values[1]:
        raise ValueError("Header audit tidak ditemukan pada tab Unmatched_GL.")
    records: list[dict[str, Any]] = []
    for row_number, row in enumerate(values[2:], start=3):
        first = _cell(row, 0)
        if first.startswith("Total nominal") or first.startswith("DEBET PERLU DICEK"):
            break
        if first.startswith("Semua transaksi KREDIT ter-match"):
            continue
        txn_type = _cell(row, 3).upper()
        if txn_type not in {"", "SETTLEMENT", "REFUND", "ADJUSTMENT"}:
            continue
        reason = _cell(row, 5) or "unspecified"
        amount = _money(_cell(row, 4), f"Unmatched_GL!E{row_number}")
        records.append({"txn_type": txn_type, "reason": reason, "amount": amount})
    return records


def _reconciliation(values: list[list[str]]) -> dict[str, Any]:
    for row in values:
        if _cell(row, 0).casefold() != "rekonsiliasi":
            continue
        status = _cell(row, 1)
        if status.casefold().strip() == "selisih = 0":
            return {"reconcile_ok": True, "reconcile_diff": 0.0, "diff_total": 0.0}
        match = re.search(r"\(([^)]+)\)", status)
        difference = _money(match.group(1), "Dashboard!B Rekonsiliasi") if match else None
        return {"reconcile_ok": False, "reconcile_diff": difference, "diff_total": difference}
    raise ValueError("Status 'Rekonsiliasi' tidak ditemukan pada tab Dashboard.")


def load_chat_artifacts_from_sheets(
    *,
    client: Any = None,
    spreadsheet_key: str | None = None,
) -> dict[str, Any]:
    """Read report tabs, then retain only safe row fields and Python-computed metrics."""
    key = spreadsheet_key or config.SPREADSHEET_KEY
    if not key:
        raise ValueError("SPREADSHEET_KEY belum dikonfigurasi; isi .env untuk membaca Google Sheets.")
    sheets_client = client if client is not None else create_sheets_client(read_only=True)
    try:
        spreadsheet = sheets_client.open_by_key(key)
    except Exception as error:
        logger.exception("Unable to open configured Google spreadsheet")
        raise RuntimeError("Gagal membuka Google Sheets; periksa SPREADSHEET_KEY dan izin akun service.") from error

    result_rows = _result_rows(_read_sheet(spreadsheet, "Working_Paper_Result"))
    unmatched_rows = _unmatched_rows(_read_sheet(spreadsheet, "Unmatched_GL"))
    reconcile_result = _reconciliation(_read_sheet(spreadsheet, "Dashboard"))
    df_result = pd.DataFrame(result_rows, columns=_RESULT_COLUMNS)
    df_unmatched = pd.DataFrame(unmatched_rows, columns=("txn_type", "reason", "amount"))
    metrics = compute_metrics(df_result, reconcile_result, df_unmatched)
    return {
        "df_result": df_result,
        "df_unmatched": df_unmatched,
        "metrics": metrics,
        "reconcile_result": reconcile_result,
        "source": "Google Sheets",
    }
