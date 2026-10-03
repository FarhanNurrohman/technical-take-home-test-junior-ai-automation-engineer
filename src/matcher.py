from __future__ import annotations

import math
import re
from typing import Any

import pandas as pd

from src.config import ADJUSTMENT_MODE, AMOUNT_TOLERANCE, SIMILARITY_THRESHOLD
from src.parsing import extract_pengajuan
from src.scoring import normalize_for_matching, score

normalize_for_matching = normalize_for_matching


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clean_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _coerce_target_records(df_targets: pd.DataFrame) -> list[dict[str, Any]]:
    return df_targets.to_dict(orient="records")


def build_targets(df_wp: pd.DataFrame, df_gl: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build target rows for WP advances and grouped April NEW_ADVANCE transactions."""
    wp_rows = df_wp.copy() if df_wp is not None else pd.DataFrame(columns=["wp_row", "date", "voucher_no", "description", "amount"])
    gl_rows = df_gl.copy() if df_gl is not None else pd.DataFrame(columns=["gl_row", "date", "voucher_no", "description", "debit", "credit", "txn_type", "po_codes", "pengajuan_code", "pengajuan_month"])

    targets: list[dict[str, Any]] = []
    for _, row in wp_rows.iterrows():
        description = _clean_text(row.get("description"))
        target_id = f"WP-{int(row.get('wp_row', 0))}"
        pengajuan_code, pengajuan_month = extract_pengajuan(description)
        targets.append(
            {
                "target_id": target_id,
                "target_type": "WP",
                "wp_row": int(row.get("wp_row", 0)),
                "date": row.get("date"),
                "voucher_no": row.get("voucher_no"),
                "description": description,
                "amount": _to_float(row.get("amount")),
                "po_codes": [code.upper() for code in row.get("po_codes", [])] if isinstance(row.get("po_codes"), list) else [],
                "pengajuan_code": pengajuan_code,
                "pengajuan_month": pengajuan_month,
                "grouped_rows": [int(row.get("wp_row", 0))],
            }
        )

    new_advance_rows = gl_rows[gl_rows.get("txn_type") == "NEW_ADVANCE"].copy() if "txn_type" in gl_rows.columns else pd.DataFrame()
    new_advances: dict[str, dict[str, Any]] = {}
    for _, row in new_advance_rows.iterrows():
        codes = row.get("po_codes") if isinstance(row.get("po_codes"), list) else []
        grouped_codes = [str(code).upper() for code in codes if str(code).strip()]
        if not grouped_codes:
            key = f"NEW-{int(row.get('gl_row', 0))}"
            bucket = new_advances.setdefault(
                key,
                {
                    "target_id": key,
                    "target_type": "NEW_ADVANCE",
                    "wp_row": None,
                    "date": row.get("gl_date"),
                    "voucher_no": "",
                    "description": _clean_text(row.get("description")),
                    "amount": 0.0,
                    "po_codes": [],
                    "pengajuan_code": None,
                    "pengajuan_month": None,
                    "grouped_rows": [],
                },
            )
            bucket["amount"] += _to_float(row.get("debit"))
            bucket["grouped_rows"].append(int(row.get("gl_row", 0)))
            bucket["voucher_no"] = ", ".join(sorted({str(value) for value in [bucket["voucher_no"], row.get("voucher_no")] if value not in (None, "")}, key=str.lower))
            continue

        for code in grouped_codes:
            key = f"NEW-{code}"
            bucket = new_advances.setdefault(
                key,
                {
                    "target_id": key,
                    "target_type": "NEW_ADVANCE",
                    "wp_row": None,
                    "date": row.get("gl_date"),
                    "voucher_no": "",
                    "description": _clean_text(row.get("description")),
                    "amount": 0.0,
                    "po_codes": [code],
                    "pengajuan_code": None,
                    "pengajuan_month": None,
                    "grouped_rows": [],
                },
            )
            bucket["amount"] += _to_float(row.get("debit"))
            bucket["grouped_rows"].append(int(row.get("gl_row", 0)))
            bucket["voucher_no"] = ", ".join(sorted({str(value) for value in [bucket["voucher_no"], row.get("voucher_no")] if value not in (None, "")}, key=str.lower))
            bucket["date"] = min([bucket["date"], row.get("gl_date")], key=lambda value: value if value is not None else pd.Timestamp.max)
            pengajuan_code, pengajuan_month = extract_pengajuan(_clean_text(row.get("description")))
            if pengajuan_code is not None:
                bucket["pengajuan_code"] = pengajuan_code
                bucket["pengajuan_month"] = pengajuan_month

    targets.extend(new_advances.values())

    df_targets = pd.DataFrame(targets, columns=[
        "target_id",
        "target_type",
        "wp_row",
        "date",
        "voucher_no",
        "description",
        "amount",
        "po_codes",
        "pengajuan_code",
        "pengajuan_month",
        "grouped_rows",
    ])
    df_targets["wp_row"] = df_targets["wp_row"].where(pd.notna(df_targets["wp_row"]), None)
    df_targets["amount"] = df_targets["amount"].fillna(0.0)

    debit_exceptions = gl_rows[gl_rows.get("txn_type") == "UNCLASSIFIED_DEBIT"].copy() if "txn_type" in gl_rows.columns else pd.DataFrame()
    if not debit_exceptions.empty:
        debit_exceptions = debit_exceptions.reset_index(drop=True)

    return df_targets, debit_exceptions


def match_gl_to_targets(df_gl: pd.DataFrame, df_targets: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Match each eligible GL row to a single target according to the business rules."""
    gl_rows = df_gl.copy() if df_gl is not None else pd.DataFrame()
    if gl_rows.empty:
        return pd.DataFrame(columns=["gl_row", "target_id", "match_type", "confidence", "txn_type", "voucher_no"]), pd.DataFrame(columns=["gl_row", "voucher_no", "description", "txn_type", "reason"])

    target_rows = _coerce_target_records(df_targets)
    match_rows: list[dict[str, Any]] = []
    unmatched_rows: list[dict[str, Any]] = []
    used_rows: set[int] = set()

    for _, row in gl_rows.iterrows():
        gl_row = int(row.get("gl_row", 0))
        if gl_row in used_rows:
            continue
        txn_type = str(row.get("txn_type") or "")
        if txn_type not in {"SETTLEMENT", "REFUND", "ADJUSTMENT"}:
            continue

        description = _clean_text(row.get("description"))
        po_codes = [str(code).upper() for code in row.get("po_codes", []) if str(code).strip()]
        pengajuan_code = _clean_text(row.get("pengajuan_code")).upper() or None
        pengajuan_month = row.get("pengajuan_month")
        assigned = False

        if po_codes:
            matching_targets = [
                target
                for target in target_rows
                if any(code in (target.get("po_codes") or []) for code in po_codes)
            ]
            if matching_targets:
                target = matching_targets[0]
                match_rows.append(
                    {
                        "gl_row": gl_row,
                        "target_id": target["target_id"],
                        "match_type": "PO",
                        "confidence": 1.0,
                        "txn_type": txn_type,
                        "voucher_no": row.get("voucher_no"),
                        "description": description,
                    }
                )
                used_rows.add(gl_row)
                assigned = True
            else:
                unmatched_rows.append(
                    {"gl_row": gl_row, "voucher_no": row.get("voucher_no"), "description": description, "txn_type": txn_type, "reason": "code_unknown"}
                )
                used_rows.add(gl_row)
                assigned = True

        if assigned:
            continue

        same_pengajuan = [
            target
            for target in target_rows
            if _clean_text(target.get("pengajuan_code")).upper() == str(pengajuan_code or "").upper()
        ]
        if pengajuan_code and same_pengajuan:
            if len({target["target_id"] for target in same_pengajuan}) > 1:
                unmatched_rows.append(
                    {"gl_row": gl_row, "voucher_no": row.get("voucher_no"), "description": description, "txn_type": txn_type, "reason": "pengajuan_conflict"}
                )
            else:
                target = same_pengajuan[0]
                match_rows.append(
                    {
                        "gl_row": gl_row,
                        "target_id": target["target_id"],
                        "match_type": "PENGAJUAN",
                        "confidence": 1.0,
                        "txn_type": txn_type,
                        "voucher_no": row.get("voucher_no"),
                        "description": description,
                    }
                )
                used_rows.add(gl_row)
            continue

        candidates: list[tuple[dict[str, Any], float]] = []
        for target in target_rows:
            target_desc = _clean_text(target.get("description"))
            if pengajuan_month is not None and not pd.isna(pengajuan_month):
                target_date = pd.to_datetime(target.get("date"), errors="coerce")
                if pd.isna(target_date) or int(target_date.month) != int(pengajuan_month):
                    continue
            score_value = score(description, target_desc, {"scorer": "token_jaccard"})
            if not math.isfinite(score_value):
                continue
            candidates.append((target, float(score_value)))

        if not candidates:
            reason = "month_mismatch" if pengajuan_month is not None else "no_candidate"
            unmatched_rows.append({"gl_row": gl_row, "voucher_no": row.get("voucher_no"), "description": description, "txn_type": txn_type, "reason": reason})
            continue

        candidates.sort(key=lambda item: item[1], reverse=True)
        best_target, best_score = candidates[0]
        second_score = candidates[1][1] if len(candidates) > 1 else 0.0
        threshold = float(SIMILARITY_THRESHOLD)
        if best_score >= threshold and (best_score - second_score) >= 0.1:
            match_rows.append(
                {
                    "gl_row": gl_row,
                    "target_id": best_target["target_id"],
                    "match_type": "PHRASE",
                    "confidence": best_score,
                    "txn_type": txn_type,
                    "voucher_no": row.get("voucher_no"),
                    "description": description,
                }
            )
            used_rows.add(gl_row)
        else:
            unmatched_rows.append({"gl_row": gl_row, "voucher_no": row.get("voucher_no"), "description": description, "txn_type": txn_type, "reason": "ambiguous"})

    df_matches = pd.DataFrame(match_rows, columns=["gl_row", "target_id", "match_type", "confidence", "txn_type", "voucher_no", "description"])
    df_unmatched = pd.DataFrame(unmatched_rows, columns=["gl_row", "voucher_no", "description", "txn_type", "reason"])
    detail_columns = [column for column in ("gl_row", "gl_date", "credit", "debit") if column in gl_rows.columns]
    if "gl_row" in detail_columns:
        unmatched_details = gl_rows[detail_columns].drop_duplicates(subset="gl_row")
        df_unmatched = df_unmatched.merge(unmatched_details, on="gl_row", how="left", validate="one_to_one")
    return df_matches, df_unmatched


def aggregate_realizations(df_targets: pd.DataFrame, df_matches: pd.DataFrame, df_gl: pd.DataFrame) -> pd.DataFrame:
    """Aggregate matched GL entries per target and compute the displayed realization fields."""
    targets = df_targets.copy() if df_targets is not None else pd.DataFrame(columns=["target_id", "target_type", "amount", "description", "po_codes", "pengajuan_code", "pengajuan_month"])
    matches = df_matches.copy() if df_matches is not None else pd.DataFrame(columns=["gl_row", "target_id", "match_type", "confidence", "txn_type", "voucher_no", "description"])
    gl_rows = df_gl.copy() if df_gl is not None else pd.DataFrame(columns=["gl_row", "gl_date", "voucher_no", "description", "debit", "credit", "txn_type"]) 

    results: list[dict[str, Any]] = []
    for _, target in targets.iterrows():
        target_id = target.get("target_id")
        matched_gl = gl_rows[gl_rows["gl_row"].isin(matches.loc[matches["target_id"] == target_id, "gl_row"])] if not matches.empty else pd.DataFrame()
        if matched_gl.empty:
            amount = _to_float(target.get("amount"))
            results.append(
                {
                    "target_id": target_id,
                    "target_type": target.get("target_type"),
                    "wp_row": target.get("wp_row"),
                    "date": target.get("date"),
                    "voucher_no": target.get("voucher_no"),
                    "description": target.get("description"),
                    "amount": amount,
                    "realization_date": None,
                    "realization_voucher_no": "",
                    "realization_amount": 0.0,
                    "balance": amount,
                    "status": "UNSETTLED",
                    "settlement_total": 0.0,
                    "refund_total": 0.0,
                    "adjustment_total": 0.0,
                    "amount_check": None,
                    "need_settlement_evidence": False,
                    "note": "",
                    "section": "WP" if str(target.get("target_type")) == "WP" else "NEW_ADVANCE",
                }
            )
            continue

        settlement_total = float(matched_gl.loc[matched_gl["txn_type"] == "SETTLEMENT", "credit"].sum())
        refund_total = float(matched_gl.loc[matched_gl["txn_type"] == "REFUND", "credit"].sum())
        adjustment_total = float(matched_gl.loc[matched_gl["txn_type"] == "ADJUSTMENT", "debit"].sum())
        if ADJUSTMENT_MODE == "ignore":
            adjustment_total = 0.0
        credit_total = float(matched_gl["credit"].sum())
        realization_total = credit_total - adjustment_total
        amount = _to_float(target.get("amount"))
        balance = amount - realization_total
        if balance < -AMOUNT_TOLERANCE:
            status = "OVER_SETTLED"
        elif abs(balance) <= AMOUNT_TOLERANCE:
            status = "SETTLED"
        elif realization_total > 0:
            status = "PARTIAL"
        else:
            status = "UNSETTLED"

        realization_dates = pd.to_datetime(
            matched_gl.loc[matched_gl["txn_type"].isin(["SETTLEMENT", "REFUND"]), "gl_date"].dropna(), errors="coerce"
        )
        realization_date = realization_dates.max() if not realization_dates.empty else pd.NaT
        voucher_values: list[str] = []
        seen: set[str] = set()
        for _, current in matched_gl.sort_values("gl_date").iterrows():
            voucher = _clean_text(current.get("voucher_no"))
            if not voucher:
                continue
            if current.get("txn_type") == "ADJUSTMENT":
                voucher = f"{voucher} (koreksi)"
            if voucher not in seen:
                seen.add(voucher)
                voucher_values.append(voucher)
        realization_voucher = ", ".join(voucher_values)

        amount_check = None
        if settlement_total > 0:
            amount_check = "EXACT" if abs(settlement_total - amount) <= AMOUNT_TOLERANCE else "DIFF"

        has_refund = (matched_gl["txn_type"] == "REFUND").any()
        has_settlement = (matched_gl["txn_type"] == "SETTLEMENT").any()
        need_settlement_evidence = realization_total > 0 and has_refund and not has_settlement
        note = ""
        adjustment_rows = matched_gl[matched_gl["txn_type"] == "ADJUSTMENT"]
        if not adjustment_rows.empty:
            adjustment_voucher = ", ".join(sorted({str(value) for value in adjustment_rows["voucher_no"].dropna() if str(value).strip()}))
            note = f"Koreksi debit Rp {adjustment_total:,.0f} ({adjustment_voucher})"
        elif need_settlement_evidence:
            note = "Pengembalian saja; belum ada settlement belanja di GL"

        results.append(
            {
                "target_id": target_id,
                "target_type": target.get("target_type"),
                "wp_row": target.get("wp_row"),
                "date": target.get("date"),
                "voucher_no": target.get("voucher_no"),
                "description": target.get("description"),
                "amount": amount,
                "realization_date": pd.NaT if pd.isna(realization_date) else realization_date,
                "realization_voucher_no": realization_voucher,
                "realization_amount": realization_total,
                "balance": balance,
                "status": status,
                "settlement_total": settlement_total,
                "refund_total": refund_total,
                "adjustment_total": adjustment_total,
                "amount_check": amount_check,
                "need_settlement_evidence": bool(need_settlement_evidence),
                "note": note,
                "section": "WP" if str(target.get("target_type")) == "WP" else "NEW_ADVANCE",
            }
        )

    df_result = pd.DataFrame(results)
    if df_result.empty:
        return df_result
    expected_order = [
        "target_id",
        "target_type",
        "wp_row",
        "date",
        "voucher_no",
        "description",
        "amount",
        "realization_date",
        "realization_voucher_no",
        "realization_amount",
        "balance",
        "status",
        "settlement_total",
        "refund_total",
        "adjustment_total",
        "amount_check",
        "need_settlement_evidence",
        "note",
        "section",
    ]
    for column in expected_order:
        if column not in df_result.columns:
            df_result[column] = None
    return df_result[expected_order]


def summarize_sections(df_result: pd.DataFrame) -> pd.DataFrame:
    """Summarize result by section (WP vs NEW_ADVANCE)."""
    if df_result is None or df_result.empty:
        return pd.DataFrame(columns=["section", "rows", "amount_total", "realization_total", "balance_total"])
    summary = df_result.groupby("section", dropna=False).agg(
        rows=("target_id", "count"),
        amount_total=("amount", "sum"),
        realization_total=("realization_amount", "sum"),
        balance_total=("balance", "sum"),
    ).reset_index()
    return summary


def reconcile(df_gl: pd.DataFrame, df_matches: pd.DataFrame, df_unmatched: pd.DataFrame, df_targets: pd.DataFrame) -> dict[str, float | int | str]:
    """Verify that total GL credit equals matched + unmatched credits and report any delta."""
    gl_rows = df_gl.copy() if df_gl is not None else pd.DataFrame(columns=["gl_row", "credit", "debit", "txn_type"])
    matches = df_matches.copy() if df_matches is not None else pd.DataFrame(columns=["gl_row", "target_id", "match_type"])
    unmatched = df_unmatched.copy() if df_unmatched is not None else pd.DataFrame(columns=["gl_row", "reason"])
    target_rows = df_targets.copy() if df_targets is not None else pd.DataFrame(columns=["target_id", "amount", "target_type"])

    total_credit_gl = float(gl_rows[gl_rows["credit"] > 0]["credit"].sum()) if "credit" in gl_rows.columns else 0.0
    matched_credit = 0.0
    if "gl_row" in matches.columns and "credit" in gl_rows.columns:
        matched_credit = float(gl_rows[gl_rows["gl_row"].isin(matches["gl_row"])]["credit"].sum())
    unmatched_credit = 0.0
    if "gl_row" in unmatched.columns and "credit" in gl_rows.columns:
        unmatched_credit = float(gl_rows[gl_rows["gl_row"].isin(unmatched["gl_row"])]["credit"].sum())

    total_adjustment_debit = float(gl_rows.loc[gl_rows.get("txn_type") == "ADJUSTMENT", "debit"].sum()) if "txn_type" in gl_rows.columns and "debit" in gl_rows.columns else 0.0
    total_new_advance_debit = float(target_rows.loc[target_rows.get("target_type") == "NEW_ADVANCE", "amount"].sum()) if "target_type" in target_rows.columns and "amount" in target_rows.columns else 0.0

    diff_total = abs(total_credit_gl - (matched_credit + unmatched_credit))
    if diff_total > AMOUNT_TOLERANCE:
        raise ValueError(f"Reconciliation failed: total_credit_gl={total_credit_gl}, matched+unmatched={matched_credit + unmatched_credit}, diff={diff_total}")

    return {
        "total_credit_gl": total_credit_gl,
        "matched_credit_gl": matched_credit,
        "unmatched_credit_gl": unmatched_credit,
        "total_adjustment_debit": total_adjustment_debit,
        "total_new_advance_debit": total_new_advance_debit,
        "diff_total": diff_total,
    }


def suggest_settlement_candidates(df_result: pd.DataFrame, df_gl: pd.DataFrame, df_unmatched: pd.DataFrame) -> pd.DataFrame:
    """Return candidate unmatched credits for partial or unsettled WP targets needing proof."""
    if df_result is None or df_result.empty or df_gl is None or df_gl.empty:
        return pd.DataFrame(columns=["target_id", "gl_row", "voucher_no", "credit", "alasan"])

    candidates: list[dict[str, Any]] = []
    unmatched = df_unmatched.copy() if df_unmatched is not None else pd.DataFrame(columns=["gl_row", "voucher_no", "description", "reason"])
    gl_rows = df_gl.copy()
    unmatched_gl = gl_rows[gl_rows["gl_row"].isin(unmatched["gl_row"])] if "gl_row" in unmatched.columns else pd.DataFrame(columns=["gl_row", "voucher_no", "description", "credit"])

    for _, row in df_result.iterrows():
        if str(row.get("status") or "") not in {"PARTIAL", "UNSETTLED"}:
            continue
        if not bool(row.get("need_settlement_evidence")):
            continue

        target_amount = _to_float(row.get("amount"))
        realization_total = _to_float(row.get("realization_amount"))
        due_amount = target_amount - realization_total
        for _, credit_row in unmatched_gl.iterrows():
            credit_amount = _to_float(credit_row.get("credit"))
            if credit_amount <= 0:
                continue
            matches_amount = abs(credit_amount - due_amount) <= AMOUNT_TOLERANCE or abs(credit_amount - target_amount) <= AMOUNT_TOLERANCE
            unit_match = False
            target_desc = _clean_text(row.get("description"))
            gl_desc = _clean_text(credit_row.get("description"))
            target_units = set(re.findall(r"\bSM\s*(\d{3,4})\b", target_desc, re.IGNORECASE))
            credit_units = set(re.findall(r"\bSM\s*(\d{3,4})\b", gl_desc, re.IGNORECASE))
            if target_units and credit_units and (target_units & credit_units):
                unit_match = True
            if matches_amount or unit_match:
                candidates.append(
                    {
                        "target_id": row.get("target_id"),
                        "gl_row": int(credit_row.get("gl_row", 0)),
                        "voucher_no": credit_row.get("voucher_no"),
                        "credit": credit_amount,
                        "alasan": "amount matches remaining balance" if matches_amount else "same unit code",
                    }
                )

    return pd.DataFrame(candidates, columns=["target_id", "gl_row", "voucher_no", "credit", "alasan"])
