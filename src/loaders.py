"""Workbook input loading and GL balance integrity checks."""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import AMOUNT_TOLERANCE
from src.parsing import parse_amount

logger = logging.getLogger(__name__)

_GL_HEADERS = ("TANGGAL", "NO JURNAL", "DESKRIPSI", "DEBET-IDR", "KREDIT-IDR", "SALDO-IDR")
_WP_COLUMNS = (
	"wp_row",
	"date",
	"voucher_no",
	"description",
	"amount",
	"realization_date",
	"realization_voucher_no",
	"realization_amount",
	"balance",
	"notes",
)


def read_raw(path: str | Path) -> pd.DataFrame:
	"""Read the first worksheet as a headerless raw frame."""
	source = Path(path)
	suffix = source.suffix.lower()
	if suffix == ".xls":
		engine = "xlrd"
	elif suffix == ".xlsx":
		engine = "openpyxl"
	else:
		raise ValueError(f"Unsupported workbook extension: {source.suffix}")
	try:
		return pd.read_excel(source, header=None, dtype=object, engine=engine)
	except Exception as error:
		logger.exception("Failed to read workbook %s", source.name)
		raise ValueError(f"Unable to read workbook {source.name}: {error}") from error


def _is_missing(value: Any) -> bool:
	if value is None:
		return True
	try:
		return bool(pd.isna(value))
	except (TypeError, ValueError):
		return False


def _is_blank(value: Any) -> bool:
	return _is_missing(value) or (isinstance(value, str) and not value.strip())


def _find_gl_header(df_raw: pd.DataFrame) -> tuple[int, dict[str, int]]:
	expected = {name: name for name in _GL_HEADERS}
	for row_index, row in df_raw.iterrows():
		values = {
			str(value).strip().upper(): int(column_index)
			for column_index, value in row.items()
			if not _is_blank(value)
		}
		if all(name in values for name in expected):
			return int(row_index), {name: values[name] for name in expected}
	raise ValueError("GL header not found; expected TANGGAL, NO JURNAL, DESKRIPSI, DEBET-IDR, KREDIT-IDR, SALDO-IDR")


def _parse_gl_date(value: Any, gl_row: int) -> Any:
	if _is_blank(value) or (isinstance(value, str) and value.strip() == "-"):
		return pd.NaT
	if isinstance(value, (datetime, date, pd.Timestamp)):
		return pd.Timestamp(value)
	try:
		return pd.to_datetime(value, format="%m/%d/%Y", errors="raise")
	except (TypeError, ValueError) as error:
		logger.exception("Invalid GL date at Excel row %d", gl_row)
		raise ValueError(f"Invalid GL date at Excel row {gl_row}: {value!r}") from error


def _is_summary_row(values: list[Any]) -> bool:
	text = " ".join(str(value).strip().upper() for value in values if not _is_blank(value))
	return any(marker in text for marker in ("SALDO AWAL", "BEGINNING BALANCE", "TOTAL DEBET", "TOTAL KREDIT", "GRAND TOTAL"))


def parse_gl_frame(df_raw: pd.DataFrame) -> pd.DataFrame:
	"""Normalize a raw GL sheet while preserving transaction order and Excel rows."""
	header_index, columns = _find_gl_header(df_raw)
	records: list[dict[str, Any]] = []
	dropped: dict[str, int] = {"blank": 0, "summary": 0}

	for row_index in range(header_index + 1, len(df_raw)):
		raw_values = df_raw.iloc[row_index].tolist()
		if all(_is_blank(value) for value in raw_values):
			dropped["blank"] += 1
			continue
		if _is_summary_row(raw_values):
			dropped["summary"] += 1
			continue

		excel_row = row_index + 1
		date_value = raw_values[columns["TANGGAL"]]
		records.append(
			{
				"gl_row": excel_row,
				"gl_date": _parse_gl_date(date_value, excel_row),
				"voucher_no": raw_values[columns["NO JURNAL"]],
				"description": raw_values[columns["DESKRIPSI"]],
				"debit": parse_amount(raw_values[columns["DEBET-IDR"]]),
				"credit": parse_amount(raw_values[columns["KREDIT-IDR"]]),
				"balance": parse_amount(raw_values[columns["SALDO-IDR"]]),
			}
		)

	logger.info("Parsed %d GL transactions; dropped rows: %s", len(records), dropped)
	return pd.DataFrame(records, columns=("gl_row", "gl_date", "voucher_no", "description", "debit", "credit", "balance"))


def _find_wp_header(df_raw: pd.DataFrame) -> int:
	for row_index, row in df_raw.iterrows():
		values = [str(value).strip().casefold() for value in row if not _is_blank(value)]
		if "voucher no" in values and "description" in values:
			return int(row_index)
	raise ValueError('Working Paper header not found; expected "Voucher No" and "Description"')


def _is_wp_total(values: list[Any]) -> bool:
	return any(
		isinstance(value, str) and value.strip().casefold().startswith("total")
		for value in values
	)


def parse_wp_frame(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
	"""Parse the dynamically located WP header and rows through first blank/total."""
	header_index = _find_wp_header(df_raw)
	header_row = header_index + 1
	first_index = header_index + 2
	records: list[dict[str, Any]] = []
	last_row = header_row + 1

	for row_index in range(first_index, len(df_raw)):
		values = df_raw.iloc[row_index].tolist()
		if all(_is_blank(value) for value in values):
			break
		if _is_wp_total(values):
			break
		padded = values + [None] * max(0, 9 - len(values))
		excel_row = row_index + 1
		records.append(
			{
				"wp_row": excel_row,
				"date": padded[0],
				"voucher_no": padded[1],
				"description": padded[2],
				"amount": parse_amount(padded[3]),
				"realization_date": padded[4],
				"realization_voucher_no": padded[5],
				"realization_amount": padded[6],
				"balance": padded[7],
				"notes": padded[8],
			}
		)
		last_row = excel_row

	meta = {"header_row": header_row, "first_row": header_row + 2, "last_row": last_row if records else header_row + 1}
	logger.info(
		"Working Paper rows detected: header=%d, data=%d-%d",
		meta["header_row"],
		meta["first_row"],
		meta["last_row"],
	)
	return pd.DataFrame(records, columns=_WP_COLUMNS), meta


def load_gl(path: str | Path) -> pd.DataFrame:
	"""Load and normalize all GL transaction rows from an Excel workbook."""
	return parse_gl_frame(read_raw(path))


def load_working_paper(path: str | Path) -> tuple[pd.DataFrame, dict[str, int]]:
	"""Load the original WP rows and report detected header/data row numbers."""
	frame, meta = parse_wp_frame(read_raw(path))
	if (meta["header_row"], meta["first_row"], meta["last_row"]) != (6, 6, 20):
		logger.warning(
			"Detected WP layout differs from legacy Row 6-20 reference: header=%d, data=%d-%d; "
			"dynamic SPEC layout is retained",
			meta["header_row"],
			meta["first_row"],
			meta["last_row"],
		)
	return frame, meta


def check_gl_balance_integrity(df_gl: pd.DataFrame) -> pd.DataFrame:
	"""Return rows whose running balance fails debit-credit arithmetic."""
	required = {"debit", "credit", "balance"}
	missing = required.difference(df_gl.columns)
	if missing:
		raise ValueError(f"GL frame missing balance columns: {', '.join(sorted(missing))}")
	if len(df_gl) < 2:
		return df_gl.iloc[0:0].copy().assign(expected_balance=pd.Series(dtype=float), balance_difference=pd.Series(dtype=float))

	inconsistent: list[dict[str, Any]] = []
	for position in range(1, len(df_gl)):
		previous = df_gl.iloc[position - 1]
		current = df_gl.iloc[position]
		values = [previous["balance"], current["debit"], current["credit"], current["balance"]]
		if any(_is_missing(value) for value in values):
			row_label = current.get("gl_row", position + 1)
			raise ValueError(f"Missing GL balance input at row {row_label}")
		expected = float(previous["balance"]) + float(current["debit"]) - float(current["credit"])
		difference = float(current["balance"]) - expected
		if abs(difference) > AMOUNT_TOLERANCE:
			record = current.to_dict()
			record["expected_balance"] = expected
			record["balance_difference"] = difference
			inconsistent.append(record)
	return pd.DataFrame(inconsistent, columns=[*df_gl.columns, "expected_balance", "balance_difference"])