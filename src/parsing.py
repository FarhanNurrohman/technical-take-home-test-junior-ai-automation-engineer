"""Pure parsing and GL classification helpers."""

from __future__ import annotations

import math
import re
from typing import Any

import pandas as pd

from src.config import PENGAJUAN_PATTERN, PO_PATTERNS, ROMAN_MONTHS


_PO_REGEXES = tuple(re.compile(pattern, re.IGNORECASE) for pattern in PO_PATTERNS)
_PENGAJUAN_REGEX = re.compile(PENGAJUAN_PATTERN, re.IGNORECASE)


def parse_amount(value: Any) -> float:
    """Convert common Indonesian and international currency formats to float."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else 0.0
    if pd.isna(value):
        return 0.0

    text = str(value).strip().replace("\u00a0", "")
    if not text or text == "-":
        return 0.0

    is_negative = text.startswith("(") and text.endswith(")")
    if is_negative:
        text = text[1:-1].strip()
    text = re.sub(r"(?i)\bRp\b", "", text).replace(" ", "")
    text = re.sub(r"[^0-9,.+-]", "", text)
    if not text or text in {"+", "-", ".", ","}:
        raise ValueError(f"Invalid monetary value: {value!r}")

    if "," in text and "." in text:
        decimal_separator = "," if text.rfind(",") > text.rfind(".") else "."
        grouping_separator = "." if decimal_separator == "," else ","
        text = text.replace(grouping_separator, "")
        if decimal_separator == ",":
            text = text.replace(",", ".")
    elif "," in text or "." in text:
        separator = "," if "," in text else "."
        pieces = text.split(separator)
        if len(pieces) > 2:
            text = "".join(pieces)
        elif len(pieces[-1]) == 3:
            text = "".join(pieces)
        else:
            text = ".".join(pieces)

    try:
        amount = float(text)
    except ValueError as error:
        raise ValueError(f"Invalid monetary value: {value!r}") from error
    return -abs(amount) if is_negative else amount


def extract_po_codes(text: Any) -> list[str]:
    """Extract every PO/WO/SPK/PGJ code from a value in uppercase."""
    if text is None or pd.isna(text):
        return []
    source = str(text)
    return [match.upper() for regex in _PO_REGEXES for match in regex.findall(source)]


def extract_pengajuan(text: Any) -> tuple[str | None, int | None]:
    """Return the first application code and its Roman-numeral month."""
    if text is None or pd.isna(text):
        return None, None
    match = _PENGAJUAN_REGEX.search(str(text))
    if match is None:
        return None, None
    code = match.group(0).upper()
    month_token = code.rsplit("/", 2)[1]
    return code, ROMAN_MONTHS[month_token]


def classify_gl_rows(df_gl: pd.DataFrame, wp_po_codes: set[str]) -> pd.DataFrame:
    """Add PO/application codes and classify rows using GL debit/credit first."""
    required = {"voucher_no", "description", "debit", "credit"}
    missing = required.difference(df_gl.columns)
    if missing:
        raise ValueError(f"GL frame missing required columns: {', '.join(sorted(missing))}")

    known_codes = {str(code).upper() for code in wp_po_codes}
    result = df_gl.copy()
    po_codes_column: list[list[str]] = []
    application_codes: list[str | None] = []
    application_months: list[int | None] = []
    transaction_types: list[str] = []

    for _, row in result.iterrows():
        description = row["description"]
        safe_description = "" if description is None or pd.isna(description) else str(description)
        po_codes = extract_po_codes(safe_description)
        application_code, application_month = extract_pengajuan(safe_description)
        debit = parse_amount(row["debit"])
        credit = parse_amount(row["credit"])
        voucher = "" if pd.isna(row["voucher_no"]) else str(row["voucher_no"]).upper()

        if credit > 0:
            transaction_type = "REFUND" if "PENGEMBALIAN" in safe_description.upper() else "SETTLEMENT"
        elif debit > 0 and "PENGEMBALIAN" in safe_description.upper():
            transaction_type = "ADJUSTMENT"
        elif debit > 0 and (
            voucher.startswith("ADV/") or any(code not in known_codes for code in po_codes)
        ):
            transaction_type = "NEW_ADVANCE"
        else:
            transaction_type = "UNCLASSIFIED_DEBIT"

        po_codes_column.append(po_codes)
        application_codes.append(application_code)
        application_months.append(application_month)
        transaction_types.append(transaction_type)

    result["txn_type"] = transaction_types
    result["po_codes"] = po_codes_column
    result["pengajuan_code"] = application_codes
    result["pengajuan_month"] = application_months
    return result