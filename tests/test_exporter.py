import json
import re

import pandas as pd
import pytest

from src.sheets_exporter import (
	build_dashboard_payload,
	build_result_payload,
	build_unmatched_payload,
	export_to_sheets,
)
from src.matcher import aggregate_realizations, build_targets, match_gl_to_targets


@pytest.fixture
def sample_result():
	return pd.DataFrame(
		[
			{
				"target_id": "WP-8",
				"target_type": "WP",
				"wp_row": 8,
				"date": "2026-01-22",
				"voucher_no": "PMT2/BK/2601/0001",
				"description": "STYLING SM 1127 (STUDIO)",
				"amount": 1_583_700,
				"realization_date": pd.Timestamp("2026-04-27"),
				"realization_voucher_no": "PMT2/BM/2604/0008, KK/HO/2604/0006 (koreksi)",
				"realization_amount": 268_000,
				"balance": 1_315_700,
				"status": "PARTIAL",
				"settlement_total": 0,
				"refund_total": 308_000,
				"adjustment_total": 40_000,
				"amount_check": None,
				"need_settlement_evidence": True,
				"note": "Koreksi debit Rp 40.000",
				"section": "WP",
			},
			{
				"target_id": "NEW-TP01/PO/26040001",
				"target_type": "NEW_ADVANCE",
				"wp_row": None,
				"date": "2026-04-01",
				"voucher_no": "ADV/BK/2604/0001",
				"description": "=SUM(A1)",
				"amount": 100_000,
				"realization_amount": 0,
				"balance": 100_000,
				"status": "UNSETTLED",
				"section": "NEW_ADVANCE",
			},
		]
	)


@pytest.fixture
def sample_metrics():
	return {
		"wp": {"total_advance": 1_583_700, "total_realization": 268_000, "total_balance": 1_315_700, "unsettled_count": 1},
		"new_advance": {"total_advance": 100_000, "total_realization": 0, "total_balance": 100_000, "unsettled_count": 1},
		"unmatched_count": 1,
		"unmatched_total": 25_000,
		"need_settlement_evidence_count": 1,
		"over_settled_count": 0,
		"reconcile_ok": True,
		"reconcile_diff": 0,
		"unsettled_items": [
			{"section": "WP", "description": "Studio", "amount": 1_583_700, "realized": 268_000, "balance": 1_315_700, "status": "PARTIAL", "flags": ["need_settlement_evidence"], "suggested_action": "Minta bukti."},
			{"section": "NEW_ADVANCE", "description": "Advance baru", "amount": 100_000, "realized": 0, "balance": 100_000, "status": "UNSETTLED", "flags": [], "suggested_action": "Pantau."},
		],
	}


def test_build_result_payload_uses_dynamic_subtotals_and_single_row_sections(sample_result):
	payload = build_result_payload(sample_result)
	meta = payload["meta"]
	values = payload["values"]

	assert values[0][0] == "PT. SETIAWAN DWI TUNGGAL"
	assert values[5][4] == "Realization"
	assert any(merge.get("range") == "E6:G6" for merge in payload["merges"])
	assert meta["subtotal_a_row"] < meta["subtotal_b_row"] < meta["grand_total_row"]
	assert meta["section_a_rows"] and meta["section_b_rows"]
	assert values[meta["section_a_rows"][0] - 1][7] == f"=D{meta['section_a_rows'][0]}-G{meta['section_a_rows'][0]}"
	assert values[meta["section_b_rows"][0] - 1][7] == f"=D{meta['section_b_rows'][0]}-G{meta['section_b_rows'][0]}"
	assert isinstance(values[meta["section_a_rows"][0] - 1][6], (int, float))
	assert values[meta["subtotal_a_row"] - 1][3].startswith("=SUM(D")
	assert values[meta["subtotal_a_row"] - 1][6].startswith("=SUM(G")
	assert values[meta["grand_total_row"] - 1][3] == f"=D{meta['subtotal_a_row']}+D{meta['subtotal_b_row']}"
	assert values[meta["section_b_rows"][0] - 1][2].startswith("'")
	assert sample_result.loc[1, "description"] == "=SUM(A1)"


def test_build_result_payload_has_empty_new_advance_section():
	wp_only = pd.DataFrame([{"target_id": "WP-1", "section": "WP", "wp_row": 8, "date": "2026-01-01", "voucher_no": "V1", "description": "WP", "amount": 100, "realization_amount": 20, "balance": 80, "status": "PARTIAL"}])
	payload = build_result_payload(wp_only)
	values = payload["values"]
	meta = payload["meta"]

	assert any("Tidak ada advance baru" in str(row) for row in values)
	assert values[meta["subtotal_b_row"] - 1][3] == 0


def test_build_result_payload_formats_status_and_json_serializes_missing_values(sample_result):
	payload = build_result_payload(sample_result)
	serialized = json.dumps(payload, allow_nan=False)

	assert "PARTIAL" in serialized
	assert payload["values"][8][4] == "2026-04-27"
	assert any(spec.get("background") == "#FFF2CC" for spec in payload["formats"])


@pytest.mark.parametrize(
	("status", "color"),
	[("PARTIAL", "#FFF2CC"), ("UNSETTLED", "#FFF2CC"), ("OVER_SETTLED", "#F4CCCC"), ("SETTLED", "#D9EAD3")],
)
def test_result_payload_formats_each_status(status, color):
	frame = pd.DataFrame([{"target_id": "WP-1", "section": "WP", "wp_row": 8, "amount": 10, "realization_amount": 5, "status": status}])
	assert any(spec.get("background") == color for spec in build_result_payload(frame)["formats"])


def test_formula_evaluation_matches_python_subtotals_and_grand_total():
	wp = pd.DataFrame([{"wp_row": 8, "date": "2026-01-01", "voucher_no": "ADV-WP", "description": "TP01/PO/26010001 BAR STOOL", "amount": 100, "po_codes": ["TP01/PO/26010001"]}])
	gl = pd.DataFrame(
		[
			{"gl_row": 1, "gl_date": "2026-04-10", "voucher_no": "PMT2/BM/2604/0001", "description": "SETTLEMENT TP01/PO/26010001", "debit": 0, "credit": 25, "txn_type": "SETTLEMENT", "po_codes": ["TP01/PO/26010001"], "pengajuan_code": None, "pengajuan_month": None},
			{"gl_row": 2, "gl_date": "2026-04-11", "voucher_no": "ADV/BK/2604/0001", "description": "FR01/PO/26040004 ADVANCE BARU", "debit": 40, "credit": 0, "txn_type": "NEW_ADVANCE", "po_codes": ["FR01/PO/26040004"], "pengajuan_code": None, "pengajuan_month": None},
		]
	)
	targets, _ = build_targets(wp, gl)
	matches, _ = match_gl_to_targets(gl, targets)
	result = aggregate_realizations(targets, matches, gl)
	payload = build_result_payload(result)
	rows = payload["values"]
	meta = payload["meta"]
	section_a = meta["section_a_rows"]
	section_b = meta["section_b_rows"]

	python_a = sum(rows[row - 1][3] for row in section_a)
	python_b = sum(rows[row - 1][3] for row in section_b)
	python_a_realization = sum(rows[row - 1][6] for row in section_a)
	python_b_realization = sum(rows[row - 1][6] for row in section_b)

	def evaluate_cell(row_number, column_index):
		value = rows[row_number - 1][column_index]
		if not isinstance(value, str) or not value.startswith("="):
			return value
		formula = value[1:]
		sum_match = re.fullmatch(r"SUM\(([A-Z]+)(\d+):([A-Z]+)(\d+)\)", formula)
		if sum_match:
			start = int(sum_match.group(2))
			end = int(sum_match.group(4))
			column = ord(sum_match.group(1)) - ord("A")
			return sum(evaluate_cell(current_row, column) for current_row in range(start, end + 1))
		arithmetic_match = re.fullmatch(r"([A-Z]+)(\d+)([+-])([A-Z]+)(\d+)", formula)
		if arithmetic_match:
			left = evaluate_cell(int(arithmetic_match.group(2)), ord(arithmetic_match.group(1)) - ord("A"))
			right = evaluate_cell(int(arithmetic_match.group(5)), ord(arithmetic_match.group(4)) - ord("A"))
			return left + right if arithmetic_match.group(3) == "+" else left - right
		if formula == "0":
			return 0
		raise AssertionError(f"Formula tidak didukung evaluator test: {value}")

	assert sum(rows[row - 1][3] for row in section_a) == python_a
	assert sum(rows[row - 1][3] for row in section_b) == python_b
	assert python_a + python_b == 140
	assert python_a_realization + python_b_realization == 25
	assert rows[meta["subtotal_a_row"] - 1][3] == f"=SUM(D{section_a[0]}:D{section_a[-1]})"
	assert rows[meta["subtotal_b_row"] - 1][3] == f"=SUM(D{section_b[0]}:D{section_b[-1]})"
	assert rows[meta["grand_total_row"] - 1][3] == f"=D{meta['subtotal_a_row']}+D{meta['subtotal_b_row']}"
	assert evaluate_cell(meta["subtotal_a_row"], 3) == python_a
	assert evaluate_cell(meta["subtotal_a_row"], 6) == python_a_realization
	assert evaluate_cell(meta["subtotal_a_row"], 7) == python_a - python_a_realization
	assert evaluate_cell(meta["subtotal_b_row"], 3) == python_b
	assert evaluate_cell(meta["subtotal_b_row"], 6) == python_b_realization
	assert evaluate_cell(meta["grand_total_row"], 3) == python_a + python_b


def test_text_sanitization_and_missing_values_are_json_safe():
	unsafe = ["=SUM(A1)", "+62...", "-abc", "@x"]
	frame = pd.DataFrame(
		[
			{"target_id": "WP-1", "section": "WP", "wp_row": 8 + index, "date": pd.NaT, "voucher_no": "V", "description": text, "amount": float("nan"), "realization_date": pd.NaT, "realization_amount": float("nan"), "balance": float("nan"), "status": "UNSETTLED"}
			for index, text in enumerate(unsafe)
		]
	)
	payload = build_result_payload(frame)
	data_rows = [payload["values"][row - 1] for row in payload["meta"]["section_a_rows"]]

	assert [row[2] for row in data_rows] == [f"'{text}" for text in unsafe]
	assert all(row[0] == "" and row[4] == "" and row[3] == 0 for row in data_rows)
	json.dumps(payload, allow_nan=False)


def test_build_unmatched_payload_reports_empty_and_includes_suggestions():
	empty_payload = build_unmatched_payload(pd.DataFrame())
	filled_payload = build_unmatched_payload(
		pd.DataFrame([{"gl_row": 1, "date": "2026-04-01", "voucher_no": "GL1", "txn_type": "SETTLEMENT", "amount": 25_000, "reason": "ambiguous", "description": "Kredit"}]),
		pd.DataFrame([{"gl_row": 2, "txn_type": "UNCLASSIFIED_DEBIT", "debit": 500, "description": "Debet"}]),
		pd.DataFrame([{"target_id": "WP-8", "gl_row": 3, "voucher_no": "GL3", "amount": 700, "reason": "possible"}]),
	)

	assert any("Semua transaksi KREDIT ter-match" in str(row) for row in empty_payload["values"])
	assert any("SARAN" in str(row) for row in filled_payload["values"])
	assert any(25_000 in row for row in filled_payload["values"])


def test_unmatched_payload_uses_debit_for_adjustment_nominal():
	payload = build_unmatched_payload(
		pd.DataFrame([{"gl_row": 7, "txn_type": "ADJUSTMENT", "credit": 0, "debit": 40_000, "gl_date": "2026-04-27"}])
	)
	assert payload["values"][2][4] == 40_000


def test_build_dashboard_payload_links_kpis_and_flattens_summary(sample_result, sample_metrics):
	result_payload = build_result_payload(sample_result)
	dashboard = build_dashboard_payload(sample_metrics, "## Ringkasan\n- **Periksa** `kwitansi`", sample_result, result_payload["meta"])
	values = dashboard["values"]

	assert values[0][0] == "Dashboard Advance Settlement April 2026"
	assert values[2][1:4] == ["Advance Awal (WP)", "Advance Baru April", "Total"]
	assert values[3][1] == f"='Working_Paper_Result'!D{result_payload['meta']['subtotal_a_row']}"
	assert values[3][2] == f"='Working_Paper_Result'!D{result_payload['meta']['subtotal_b_row']}"
	assert any(isinstance(cell, str) and cell.startswith("=") and "Working_Paper_Result" in cell for row in values for cell in row)
	assert any("• Periksa kwitansi" in str(cell) for row in values for cell in row)
	assert all("**" not in str(cell) and "##" not in str(cell) for row in values for cell in row)
	assert all("A" in merge["range"] and ":F" in merge["range"] for merge in dashboard["merges"] if merge.get("purpose") == "summary")
	assert values.index(next(row for row in values if len(row) > 1 and row[1] == "Studio")) < values.index(next(row for row in values if len(row) > 1 and row[1] == "Advance baru"))
	assert dashboard["row_heights"]


def test_result_payload_matches_approved_studio_and_bedroom_fixture():
	frame = pd.DataFrame(
		[
			{"target_id": "WP-1", "section": "WP", "wp_row": 8, "date": "2026-01-01", "voucher_no": "A", "description": "STYLING SM 1127 (STUDIO)", "amount": 1_583_700, "realization_date": "2026-04-27", "realization_vouchers": "PMT2/BM/2604/0008, KK/HO/2604/0006 (koreksi)", "realization_amount": 268_000, "status": "PARTIAL", "note": "Koreksi debit Rp 40.000", "need_settlement_evidence": True},
			{"target_id": "WP-2", "section": "WP", "wp_row": 9, "date": "2026-01-01", "voucher_no": "B", "description": "STYLING SM 1132 (2 BEDROOM)", "amount": 25_695_900, "realization_amount": 2_028_300, "status": "PARTIAL", "need_settlement_evidence": True},
		]
	)
	payload = build_result_payload(frame)
	studio = payload["values"][payload["meta"]["section_a_rows"][0] - 1]
	bedroom = payload["values"][payload["meta"]["section_a_rows"][1] - 1]

	assert studio[5] == "PMT2/BM/2604/0008, KK/HO/2604/0006 (koreksi)"
	assert studio[6] == 268_000
	assert studio[7] == f"=D{payload['meta']['section_a_rows'][0]}-G{payload['meta']['section_a_rows'][0]}"
	assert "Koreksi debit Rp 40.000" in studio[8]
	assert "BUTUH BUKTI REALISASI" in studio[10]
	assert bedroom[6] == 2_028_300


def test_export_to_sheets_updates_existing_sheets_once_and_shares_only_when_requested(sample_result, sample_metrics, mocker, monkeypatch):
	class Worksheet:
		def __init__(self, title):
			self.title = title
			self.update_calls = []
			self.clear_calls = 0
			self.resize_calls = []
			self.row_count = 100
			self.col_count = 12
			self.has_merges = True

		def clear(self):
			self.clear_calls += 1

		def resize(self, rows, cols):
			if rows < self.row_count and self.has_merges:
				raise ValueError("cannot shrink worksheet before old merged cells are removed")
			self.resize_calls.append((rows, cols))
			self.row_count = rows
			self.col_count = cols

		def update(self, *args, **kwargs):
			self.update_calls.append((args, kwargs))

	class Spreadsheet:
		def __init__(self):
			self.sheets = {name: Worksheet(name) for name in ("Working_Paper_Result", "Dashboard", "Unmatched_GL", "Sheet1")}
			self.batch_updates = []
			self.share_calls = []

		def worksheet(self, title):
			return self.sheets[title]

		def add_worksheet(self, title, rows, cols):
			self.sheets[title] = Worksheet(title)
			return self.sheets[title]

		def batch_update(self, body):
			self.batch_updates.append(body)
			for worksheet in self.sheets.values():
				worksheet.has_merges = False

		def worksheets(self):
			return list(self.sheets.values())

		def reorder_worksheets(self, order):
			self.ordered = [sheet.title for sheet in order]

		def del_worksheet(self, worksheet):
			del self.sheets[worksheet.title]

		def share(self, **kwargs):
			self.share_calls.append(kwargs)

	spreadsheet = Spreadsheet()
	monkeypatch.setattr("src.sheets_exporter.config.SPREADSHEET_KEY", "test-key")
	client = mocker.Mock()
	client.open_by_key.return_value = spreadsheet
	result_meta = build_result_payload(sample_result)["meta"]
	for _ in range(2):
		export_to_sheets(sample_result, "Summary", sample_metrics, pd.DataFrame(), client=client, share_public=True, result_meta=result_meta)
	export_to_sheets(sample_result, "Summary", sample_metrics, pd.DataFrame(), client=client, share_public=False, result_meta=result_meta)

	assert len(spreadsheet.sheets) == 3
	assert spreadsheet.ordered == ["Working_Paper_Result", "Dashboard", "Unmatched_GL"]
	assert all(sheet.clear_calls == 3 for sheet in spreadsheet.sheets.values())
	assert all(len(sheet.update_calls) == 3 for sheet in spreadsheet.sheets.values())
	assert len(spreadsheet.batch_updates) == 9
	assert len(spreadsheet.share_calls) == 2


def test_missing_credentials_raise_clear_error_without_reading_secret(sample_result, sample_metrics, monkeypatch, tmp_path):
	missing = tmp_path / "missing-service-account.json"
	monkeypatch.setattr("src.sheets_exporter.config.GOOGLE_SHEETS_CRED", str(missing))

	with pytest.raises(FileNotFoundError, match="kredensial Google Sheets tidak ditemukan"):
		export_to_sheets(sample_result, "Summary", sample_metrics, pd.DataFrame())


def test_invalid_credential_json_does_not_echo_credential_contents(sample_result, sample_metrics, monkeypatch, tmp_path):
	credential_path = tmp_path / "credentials.json"
	credential_path.write_text('{"private_key":"never-show-this', encoding="utf-8")
	monkeypatch.setattr("src.sheets_exporter.config.GOOGLE_SHEETS_CRED", str(credential_path))

	with pytest.raises(ValueError, match="JSON valid") as error:
		export_to_sheets(sample_result, "Summary", sample_metrics, pd.DataFrame())
	assert "never-show-this" not in str(error.value)


def test_spreadsheet_permission_error_names_service_account(sample_result, sample_metrics, monkeypatch, mocker):
	monkeypatch.setattr("src.sheets_exporter.config.SPREADSHEET_KEY", "test-key")
	client = mocker.Mock()
	client.auth.service_account_email = "finance@example.test"
	client.open_by_key.side_effect = Exception("403 Permission denied")

	with pytest.raises(PermissionError, match="finance@example.test.*Editor"):
		export_to_sheets(sample_result, "Summary", sample_metrics, pd.DataFrame(), client=client)


def test_quota_error_retries_at_most_twice(mocker):
	from src.sheets_exporter import _run_with_retry

	operation = mocker.Mock(side_effect=[Exception("429 quota"), Exception("429 quota"), "done"])
	mocker.patch("src.sheets_exporter.time.sleep")

	assert _run_with_retry(operation) == "done"
	assert operation.call_count == 3