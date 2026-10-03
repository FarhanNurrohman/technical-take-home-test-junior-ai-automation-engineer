"""Profile the source GL and Working Paper without applying final matching."""

from __future__ import annotations

import argparse
import difflib
import logging
import re
from pathlib import Path
from typing import Any

import pandas as pd

from src.config import GL_PATH, PENGAJUAN_PATTERN, ROOT_DIR, SIMILARITY_THRESHOLD, WORKING_PAPER_PATH
from src.loaders import check_gl_balance_integrity, load_gl, load_working_paper
from src.parsing import classify_gl_rows, extract_pengajuan, extract_po_codes

logger = logging.getLogger(__name__)

PROFILE_DIR = ROOT_DIR / "data" / "_profile"
REPORT_PATH = ROOT_DIR / "docs" / "DATA_PROFILE.md"
EXPECTED_AMOUNT_SEARCHES = (
    23_667_600,
    1_275_700,
    1_315_700,
    25_695_900,
    1_583_700,
    2_028_300,
    308_000,
    40_000,
)
KEYWORDS = ("STYLING", "PBB", "SUMMARECON", "TALENTA", "DROPBOX", "SM 1132", "SM 1127")
TXN_TYPES = ("SETTLEMENT", "REFUND", "ADJUSTMENT", "NEW_ADVANCE", "UNCLASSIFIED_DEBIT")
PO_BUCKETS = ("PO ada di WP", "PO hanya ada di DEBET GL", "tanpa kode PO", "kode PO tidak dikenal")


def _safe_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value)


def clean_description(text: Any) -> str:
    """Remove generic wording while keeping useful unit and numeric tokens."""
    cleaned = _safe_text(text).upper()
    cleaned = re.sub(PENGAJUAN_PATTERN, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"PENGEMBALIAN\s+KELEBIHAN\s+DANA\s+UM", " ", cleaned)
    cleaned = re.sub(r"PENGEMBALIAN\s+ADVANCE", " ", cleaned)
    cleaned = re.sub(r"TRANSFER\s+KEKURANGAN\s+DANA\s+UM", " ", cleaned)
    cleaned = re.sub(r"\b(?:SETTLEMENT|REALISASI|PELUNASAN|ADVANCE|UANG\s+MUKA|NOMOR|NO)\b", " ", cleaned)
    cleaned = re.sub(r"\bUM\b", " ", cleaned)
    cleaned = re.sub(r"[^A-Z0-9]+", " ", cleaned)
    return " ".join(cleaned.split())


def classify_po_bucket(
    po_codes: list[str], wp_po_codes: set[str], debit_po_codes: set[str]
) -> str:
    """Classify a row's PO reference relative to WP and debit GL codes."""
    normalized_codes = {code.upper() for code in po_codes}
    normalized_wp = {code.upper() for code in wp_po_codes}
    normalized_debit = {code.upper() for code in debit_po_codes}
    if normalized_codes & normalized_wp:
        return "PO ada di WP"
    if normalized_codes & normalized_debit:
        return "PO hanya ada di DEBET GL"
    if not normalized_codes:
        return "tanpa kode PO"
    return "kode PO tidak dikenal"


def rank_wp_candidates(
    description: Any,
    pengajuan_month: int | None,
    amount: float,
    working_paper: pd.DataFrame,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """Return difflib candidate scores and month/amount indicators, not matches."""
    source = clean_description(description)
    candidates: list[dict[str, Any]] = []
    for _, wp_row in working_paper.iterrows():
        target = clean_description(wp_row.get("description"))
        score = difflib.SequenceMatcher(None, source, target).ratio() if source and target else 0.0
        wp_date = pd.to_datetime(wp_row.get("date"), errors="coerce")
        has_application_month = pengajuan_month is not None and not pd.isna(pengajuan_month)
        application_month_matches = (
            None
            if not has_application_month or pd.isna(wp_date)
            else int(wp_date.month) == int(pengajuan_month)
        )
        wp_amount = float(wp_row.get("amount", 0.0) or 0.0)
        realization_amount = wp_row.get("realization_amount", 0.0)
        if realization_amount is None or pd.isna(realization_amount):
            realization_amount = 0.0
        elif isinstance(realization_amount, str):
            try:
                realization_amount = float(realization_amount)
            except ValueError:
                realization_amount = 0.0
        remaining_amount = wp_amount - float(realization_amount)
        candidates.append(
            {
                "wp_row": wp_row.get("wp_row"),
                "wp_description": wp_row.get("description"),
                "score": score,
                "application_month_matches": application_month_matches,
                "amount_matches_amount_or_balance": any(
                    abs(float(amount) - possible_amount) <= 0.01
                    for possible_amount in (wp_amount, remaining_amount)
                ),
            }
        )
    return sorted(candidates, key=lambda candidate: candidate["score"], reverse=True)[:top_n]


def _date_month(value: Any) -> int | None:
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else int(parsed.month)


def _format_date(value: Any) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    return "" if pd.isna(parsed) else parsed.strftime("%Y-%m-%d")


def _table(frame: pd.DataFrame, columns: list[str] | None = None) -> str:
    if columns is not None:
        frame = frame.reindex(columns=columns)
    if frame.empty:
        return "_(tidak ada baris)_"
    headers = [str(column) for column in frame.columns]
    values = [[_safe_text(value).replace("|", "\\|").replace("\n", " ") for value in row] for row in frame.itertuples(index=False, name=None)]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in values)
    return "\n".join(lines)


def rank_wp_rows_against_gl(working_paper: pd.DataFrame, gl_rows: pd.DataFrame) -> pd.DataFrame:
    """Choose the strongest indicative GL credit candidate for every WP row."""
    candidate_gl = gl_rows[
        (gl_rows["credit"] > 0) | (gl_rows.get("txn_type", pd.Series(index=gl_rows.index, dtype=object)) == "ADJUSTMENT")
    ]
    ranked: list[dict[str, Any]] = []
    for _, wp_row in working_paper.iterrows():
        wp_codes = set(extract_po_codes(wp_row.get("description")))
        wp_text = clean_description(wp_row.get("description"))
        best: dict[str, Any] | None = None
        for _, gl_row in candidate_gl.iterrows():
            gl_text = clean_description(gl_row.get("description"))
            score = difflib.SequenceMatcher(None, wp_text, gl_text).ratio() if wp_text and gl_text else 0.0
            po_codes = set(gl_row.get("po_codes", extract_po_codes(gl_row.get("description"))))
            code_candidate = bool(wp_codes & po_codes)
            amount = float(gl_row.get("debit", 0.0) if gl_row.get("txn_type") == "ADJUSTMENT" else gl_row.get("credit", 0.0))
            wp_amount = float(wp_row.get("amount", 0.0) or 0.0)
            realization = wp_row.get("realization_amount", 0.0)
            if realization is None or pd.isna(realization):
                realization = 0.0
            elif isinstance(realization, str):
                try:
                    realization = float(realization)
                except ValueError:
                    realization = 0.0
            candidate = {
                "wp_row": wp_row.get("wp_row"),
                "description": wp_row.get("description"),
                "gl_row": gl_row.get("gl_row"),
                "voucher_no": gl_row.get("voucher_no"),
                "txn_type": gl_row.get("txn_type"),
                "score": score,
                "code_candidate": code_candidate,
                "month_matches": (
                    None
                    if gl_row.get("pengajuan_month") is None or pd.isna(gl_row.get("pengajuan_month"))
                    or pd.isna(pd.to_datetime(wp_row.get("date"), errors="coerce"))
                    else int(gl_row["pengajuan_month"]) == int(pd.to_datetime(wp_row["date"]).month)
                ),
                "amount_matches": abs(amount - wp_amount) <= 0.01
                or abs(amount - (wp_amount - float(realization))) <= 0.01,
            }
            if best is None or (candidate["code_candidate"], candidate["score"]) > (best["code_candidate"], best["score"]):
                best = candidate
        if best is None:
            best = {
                "wp_row": wp_row.get("wp_row"),
                "description": wp_row.get("description"),
                "gl_row": None,
                "voucher_no": None,
                "txn_type": None,
                "score": 0.0,
                "code_candidate": False,
                "month_matches": None,
                "amount_matches": False,
            }
        ranked.append(best)
    return pd.DataFrame(ranked).sort_values(
        ["code_candidate", "score"], ascending=[False, False], na_position="last"
    ).reset_index(drop=True)


def opening_balance_before_first_transaction(gl_rows: pd.DataFrame) -> float:
    """Derive the ledger balance before its first transaction from running balance."""
    if gl_rows.empty:
        return 0.0
    first = gl_rows.iloc[0]
    return float(first["balance"]) - float(first["debit"]) + float(first["credit"])


def summarize_phrase_decisions(candidates: pd.DataFrame) -> pd.DataFrame:
    """Flag phrase candidate groups that fail the preliminary uniqueness rule."""
    columns = ("gl_row", "best_wp_row", "best_score", "second_wp_row", "second_score", "status")
    if candidates.empty:
        return pd.DataFrame(columns=columns)
    decisions: list[dict[str, Any]] = []
    for gl_row, group in candidates.sort_values("score", ascending=False).groupby("gl_row", sort=False):
        best = group.iloc[0]
        second = group.iloc[1] if len(group) > 1 else None
        score_margin = float(best["score"]) - float(second["score"]) if second is not None else 1.0
        is_ambiguous = float(best["score"]) < SIMILARITY_THRESHOLD or score_margin < 0.1
        decisions.append(
            {
                "gl_row": gl_row,
                "best_wp_row": best.get("wp_row"),
                "best_score": float(best["score"]),
                "second_wp_row": None if second is None else second.get("wp_row"),
                "second_score": None if second is None else float(second["score"]),
                "status": "ambiguous" if is_ambiguous else "indicative_unique",
            }
        )
    return pd.DataFrame(decisions, columns=columns)


def build_profile(gl: pd.DataFrame, wp: pd.DataFrame, meta: dict[str, int]) -> dict[str, Any]:
    """Build all profiling tables from already loaded source frames."""
    wp_po_codes = {
        code for description in wp.get("description", pd.Series(dtype=object))
        for code in extract_po_codes(description)
    }
    classified = classify_gl_rows(gl, wp_po_codes)
    debit_po_codes = {
        code
        for codes in classified.loc[classified["debit"] > 0, "po_codes"]
        for code in codes
    }
    classified["po_codes_text"] = classified["po_codes"].map(lambda codes: ", ".join(codes))

    txn_rows: list[dict[str, Any]] = []
    for txn_type in TXN_TYPES:
        subset = classified[classified["txn_type"] == txn_type]
        txn_rows.append(
            {
                "txn_type": txn_type,
                "jumlah_baris": len(subset),
                "total_debet": float(subset["debit"].sum()),
                "total_kredit": float(subset["credit"].sum()),
            }
        )
    txn_summary = pd.DataFrame(txn_rows)

    cross_source = classified[
        (classified["credit"] > 0) | (classified["txn_type"] == "ADJUSTMENT")
    ].copy()
    cross_source["bucket"] = cross_source["po_codes"].map(
        lambda codes: classify_po_bucket(codes, wp_po_codes, debit_po_codes)
    )
    cross_source["cross_amount"] = cross_source.apply(
        lambda row: float(row["debit"] if row["txn_type"] == "ADJUSTMENT" else row["credit"]),
        axis=1,
    )
    cross_summary = (
        cross_source.groupby(["txn_type", "bucket"], dropna=False)
        .agg(jumlah_baris=("gl_row", "count"), nominal=("cross_amount", "sum"))
        .reset_index()
    )

    phrase_rows: list[dict[str, Any]] = []
    for _, gl_row in cross_source[cross_source["bucket"] == "tanpa kode PO"].iterrows():
        amount = gl_row["debit"] if gl_row["txn_type"] == "ADJUSTMENT" else gl_row["credit"]
        candidates = rank_wp_candidates(
            gl_row["description"], gl_row["pengajuan_month"], amount, wp, top_n=3
        )
        for rank, candidate in enumerate(candidates, start=1):
            phrase_rows.append(
                {
                    "gl_row": gl_row["gl_row"],
                    "tanggal": _format_date(gl_row["gl_date"]),
                    "no_jurnal": gl_row["voucher_no"],
                    "txn_type": gl_row["txn_type"],
                    "deskripsi_gl": gl_row["description"],
                    "nominal": amount,
                    "rank": rank,
                    **candidate,
                    "label": "indikatif, bukan matcher final",
                }
            )
    phrase_candidates = pd.DataFrame(phrase_rows)
    phrase_decisions = summarize_phrase_decisions(phrase_candidates)

    top_wp_candidates = rank_wp_rows_against_gl(wp, classified).head(15)

    application_rows: list[dict[str, Any]] = []
    coded_rows = classified[classified["pengajuan_code"].notna()]
    for code, group in coded_rows.groupby("pengajuan_code", sort=True):
        months = [_date_month(value) for value in group["gl_date"]]
        application_month = next(
            (int(value) for value in group["pengajuan_month"] if pd.notna(value)), None
        )
        mismatched = [
            int(row["gl_row"])
            for _, row in group.iterrows()
            if application_month is not None
            and _date_month(row["gl_date"]) is not None
            and _date_month(row["gl_date"]) != application_month
        ]
        application_rows.append(
            {
                "pengajuan_code": code,
                "pengajuan_month": application_month,
                "jumlah_baris": len(group),
                "gl_rows": ", ".join(str(int(value)) for value in group["gl_row"]),
                "voucher_no": ", ".join(_safe_text(value) for value in group["voucher_no"]),
                "bulan_tanggal_gl": ", ".join("" if month is None else str(month) for month in months),
                "duplikat": len(group) > 1,
                "baris_bulan_tidak_cocok": ", ".join(map(str, mismatched)),
            }
        )
    application_groups = pd.DataFrame(application_rows)

    amount_rows: list[dict[str, Any]] = []
    for target in EXPECTED_AMOUNT_SEARCHES:
        for _, row in classified.iterrows():
            for column in ("debit", "credit", "balance"):
                if abs(float(row[column]) - target) <= 0.01:
                    amount_rows.append(
                        {
                            "target": target,
                            "source": "GL",
                            "gl_row": row["gl_row"],
                            "voucher_no": row["voucher_no"],
                            "column": column,
                            "amount": row[column],
                        }
                    )
        for _, row in wp.iterrows():
            if abs(float(row["amount"]) - target) <= 0.01:
                amount_rows.append(
                    {
                        "target": target,
                        "source": "WP",
                        "gl_row": row["wp_row"],
                        "voucher_no": row["voucher_no"],
                        "column": "amount",
                        "amount": row["amount"],
                    }
                )
    numeric_search = pd.DataFrame(amount_rows)
    amount_search_counts = pd.DataFrame(
        [
            {"target": target, "jumlah_temuan": int((numeric_search["target"] == target).sum()) if not numeric_search.empty else 0}
            for target in EXPECTED_AMOUNT_SEARCHES
        ]
    )

    keyword_rows: list[dict[str, Any]] = []
    for keyword in KEYWORDS:
        matches = classified[classified["description"].map(
            lambda text: keyword in _safe_text(text).upper()
        )]
        for _, row in matches.iterrows():
            keyword_rows.append(
                {
                    "keyword": keyword,
                    "gl_row": row["gl_row"],
                    "tanggal": _format_date(row["gl_date"]),
                    "voucher_no": row["voucher_no"],
                    "txn_type": row["txn_type"],
                    "debit": row["debit"],
                    "credit": row["credit"],
                    "description": row["description"],
                }
            )
    keyword_search = pd.DataFrame(keyword_rows)
    keyword_counts = pd.DataFrame(
        [{"keyword": keyword, "jumlah_baris": int((keyword_search["keyword"] == keyword).sum()) if not keyword_search.empty else 0}
         for keyword in KEYWORDS]
    )

    credit_candidates: list[dict[str, Any]] = []
    wp_descriptions = [clean_description(value) for value in wp["description"]]
    for _, row in classified[classified["credit"] > 0].iterrows():
        codes = row["po_codes"]
        code_found = any(set(codes) & set(extract_po_codes(desc)) for desc in wp["description"])
        scores = [
            difflib.SequenceMatcher(None, clean_description(row["description"]), desc).ratio()
            if clean_description(row["description"]) and desc else 0.0
            for desc in wp_descriptions
        ]
        best_score = max(scores, default=0.0)
        if code_found or best_score >= 0.6:
            credit_candidates.append(
                {"gl_row": row["gl_row"], "voucher_no": row["voucher_no"], "best_phrase_score": best_score, "code_candidate": code_found}
            )
    candidate_gl_rows = {int(row["gl_row"]) for row in credit_candidates}
    wp_without_credit = []
    for _, row in wp.iterrows():
        wp_codes = set(extract_po_codes(row["description"]))
        potential = []
        for _, credit_row in classified[classified["credit"] > 0].iterrows():
            if wp_codes & set(credit_row["po_codes"]):
                potential.append(int(credit_row["gl_row"]))
            elif not credit_row["po_codes"]:
                score = difflib.SequenceMatcher(
                    None, clean_description(row["description"]), clean_description(credit_row["description"])
                ).ratio()
                if score >= 0.6:
                    potential.append(int(credit_row["gl_row"]))
        if not potential:
            wp_without_credit.append(
                {"wp_row": row["wp_row"], "voucher_no": row["voucher_no"], "description": row["description"], "amount": row["amount"]}
            )
    wp_without_credit_frame = pd.DataFrame(wp_without_credit)

    data_quality_rows: list[dict[str, Any]] = []
    for _, row in classified[classified["gl_date"].isna()].iterrows():
        data_quality_rows.append({"source": "GL", "issue": "tanggal tidak terbaca", "row": row["gl_row"], "value": row["voucher_no"]})
    for _, row in wp[pd.to_datetime(wp["date"], errors="coerce").isna()].iterrows():
        data_quality_rows.append({"source": "WP", "issue": "tanggal tidak terbaca", "row": row["wp_row"], "value": row["voucher_no"]})
    for source_name, frame, row_column in (("GL", classified, "gl_row"), ("WP", wp, "wp_row")):
        for _, row in frame[frame["description"].map(lambda value: not _safe_text(value).strip())].iterrows():
            data_quality_rows.append({"source": source_name, "issue": "deskripsi kosong", "row": row[row_column], "value": row.get("voucher_no")})
        voucher_col = frame["voucher_no"].fillna("").astype(str).str.strip()
        duplicated = voucher_col.ne("") & voucher_col.duplicated(keep=False)
        for _, row in frame[duplicated].iterrows():
            data_quality_rows.append({"source": source_name, "issue": "voucher dobel", "row": row[row_column], "value": row["voucher_no"]})
        numeric_columns = ("debit", "credit", "balance") if source_name == "GL" else ("amount",)
        for column in numeric_columns:
            for _, row in frame[frame[column] < 0].iterrows():
                data_quality_rows.append({"source": source_name, "issue": "angka negatif", "row": row[row_column], "value": f"{column}={row[column]}"})
    data_quality = pd.DataFrame(data_quality_rows, columns=("source", "issue", "row", "value"))

    integrity = check_gl_balance_integrity(classified)
    summary = {
        "gl_row_count": len(classified),
        "debit_count": int((classified["debit"] > 0).sum()),
        "debit_total": float(classified["debit"].sum()),
        "credit_count": int((classified["credit"] > 0).sum()),
        "credit_total": float(classified["credit"].sum()),
        "opening_balance": opening_balance_before_first_transaction(classified),
        "closing_balance": float(classified.iloc[-1]["balance"]) if not classified.empty else 0.0,
        "wp_count": len(wp),
        "wp_meta": meta,
        "legacy_range_differs": (meta.get("header_row"), meta.get("first_row"), meta.get("last_row")) != (6, 6, 20),
    }
    return {
        "gl": classified,
        "wp": wp,
        "summary": summary,
        "txn_summary": txn_summary,
        "cross_source": cross_source,
        "cross_summary": cross_summary,
        "phrase_candidates": phrase_candidates,
        "phrase_decisions": phrase_decisions,
        "top_wp_candidates": top_wp_candidates,
        "application_groups": application_groups,
        "amount_search": numeric_search,
        "amount_search_counts": amount_search_counts,
        "keyword_search": keyword_search,
        "keyword_counts": keyword_counts,
        "wp_without_credit": wp_without_credit_frame,
        "data_quality": data_quality,
        "integrity": integrity,
        "credit_candidates": pd.DataFrame(credit_candidates),
        "candidate_gl_rows": candidate_gl_rows,
    }


def _profile_markdown(profile: dict[str, Any]) -> str:
    summary = profile["summary"]
    gl = profile["gl"]
    wp = profile["wp"]
    credits = gl[gl["credit"] > 0].copy()
    debits = gl[gl["debit"] > 0].copy()
    credits["tanggal"] = credits["gl_date"].map(_format_date)
    debits["tanggal"] = debits["gl_date"].map(_format_date)
    wp_report = wp.copy()
    wp_report["tanggal"] = wp_report["date"].map(_format_date)
    wp_report["kode_po"] = wp_report["description"].map(lambda value: ", ".join(extract_po_codes(value)))
    wp_report["kode_pengajuan"] = wp_report["description"].map(lambda value: extract_pengajuan(value)[0])
    wp_report["bulan_pengajuan"] = wp_report["description"].map(lambda value: extract_pengajuan(value)[1])
    gl_report = gl.copy()
    gl_report["tanggal"] = gl_report["gl_date"].map(_format_date)

    sections = [
        "# Data Profile\n\nProfil dibuat dari workbook sumber untuk investigasi data. Skor frasa bersifat **indikatif, bukan matcher final**.",
        "## Ringkasan GL\n\n"
        + _table(pd.DataFrame([{
            "jumlah_baris": summary["gl_row_count"], "jumlah_debet": summary["debit_count"],
            "total_debet": summary["debit_total"], "jumlah_kredit": summary["credit_count"],
            "total_kredit": summary["credit_total"], "saldo_awal": summary["opening_balance"],
            "saldo_akhir": summary["closing_balance"],
        }]))
        + "\n\n### Per txn_type\n\n" + _table(profile["txn_summary"])
        + "\n\n### Uji integritas saldo\n\nBaris yang tidak konsisten (baris pertama tidak diuji):\n\n"
        + _table(profile["integrity"]),
        "## Seluruh Baris Kredit\n\n" + _table(credits.reindex(columns=["gl_row", "tanggal", "voucher_no", "description", "credit", "txn_type", "po_codes_text", "pengajuan_code", "pengajuan_month"]).rename(columns={"po_codes_text": "kode_po", "description": "deskripsi", "credit": "kredit", "voucher_no": "no_jurnal"})),
        "## Seluruh Baris Debet\n\n" + _table(debits.reindex(columns=["txn_type", "gl_row", "tanggal", "voucher_no", "description", "debit", "po_codes_text", "pengajuan_code", "pengajuan_month"]).rename(columns={"po_codes_text": "kode_po", "description": "deskripsi", "debit": "debet", "voucher_no": "no_jurnal"})),
        "## Working Paper\n\n"
        + f"Deteksi: header_row={summary['wp_meta']['header_row']}, first_row={summary['wp_meta']['first_row']}, last_row={summary['wp_meta']['last_row']}. "
        + ("Rentang berbeda dari acuan legacy Row 6-20." if summary["legacy_range_differs"] else "Rentang sama dengan acuan legacy Row 6-20.")
        + "\n\n" + _table(wp_report.reindex(columns=["wp_row", "tanggal", "voucher_no", "description", "amount", "kode_po", "kode_pengajuan", "bulan_pengajuan"]).rename(columns={"description": "deskripsi", "voucher_no": "voucher"})),
        "## Tabel Silang Kredit dan Adjustment\n\n" + _table(profile["cross_summary"]),
        "## Kelompok Pengajuan\n\n" + _table(profile["application_groups"]),
        "## Kandidat Frasa Tanpa Kode PO\n\n" + _table(profile["phrase_candidates"]),
        "## Status Kandidat Frasa\n\n" + _table(profile["phrase_decisions"]),
        "## Pencarian Nominal\n\n" + _table(profile["amount_search"]),
        "## Kata Kunci Deskripsi GL\n\nJumlah baris unik per kata kunci:\n\n" + _table(profile["keyword_counts"])
        + "\n\nRincian baris:\n\n" + _table(profile["keyword_search"]),
        "## WP Tanpa Kandidat Kredit\n\n" + _table(profile["wp_without_credit"]),
        "## Kualitas Data\n\n" + _table(profile["data_quality"]),
    ]
    return "\n\n".join(sections) + "\n"


def write_profile(profile: dict[str, Any], output_dir: Path = PROFILE_DIR, report_path: Path = REPORT_PATH) -> None:
    """Write the full report and CSV audit tables to ignored output paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    profile["gl"].to_csv(output_dir / "gl_profile.csv", index=False, encoding="utf-8-sig")
    profile["wp"].to_csv(output_dir / "working_paper.csv", index=False, encoding="utf-8-sig")
    profile["gl"][profile["gl"]["credit"] > 0].to_csv(output_dir / "credit_rows.csv", index=False, encoding="utf-8-sig")
    profile["gl"][profile["gl"]["debit"] > 0].to_csv(output_dir / "debit_rows.csv", index=False, encoding="utf-8-sig")
    for name in (
        "txn_summary", "cross_source", "cross_summary", "phrase_candidates", "top_wp_candidates",
        "application_groups", "phrase_decisions", "amount_search", "keyword_search", "keyword_counts",
        "amount_search_counts", "wp_without_credit", "data_quality", "integrity",
    ):
        profile[name].to_csv(output_dir / f"{name}.csv", index=False, encoding="utf-8-sig")
    report_path.write_text(_profile_markdown(profile), encoding="utf-8")
    logger.info("Wrote profile report to %s and CSV audit tables to %s", report_path, output_dir)


def _console_summary(profile: dict[str, Any]) -> str:
    summary_sections = [
        "## GL per txn_type\n\n" + _table(profile["txn_summary"]),
        "## Kredit dan Adjustment per kelompok kode\n\n" + _table(profile["cross_summary"]),
        "## 15 WP dengan kandidat tertinggi\n\n" + _table(profile["top_wp_candidates"]),
        "## Pencarian nominal: jumlah target yang ditemukan\n\n" + _table(profile["amount_search_counts"])
        + "\n\nRincian baris yang cocok:\n\n" + _table(profile["amount_search"]),
        "## Kata kunci\n\n" + _table(profile["keyword_counts"]),
        "## Saldo dan integritas\n\n"
        + f"Saldo sebelum transaksi pertama: {profile['summary']['opening_balance']:,.2f}; "
        + f"saldo setelah transaksi terakhir: {profile['summary']['closing_balance']:,.2f}; "
        + f"baris saldo tidak konsisten: {len(profile['integrity'])}.\n\n"
        + _table(profile["integrity"].reindex(columns=["gl_row", "voucher_no", "expected_balance", "balance", "balance_difference"])),
        "## Konflik dan kasus ambigu\n\n" + _table(profile["phrase_decisions"])
        + "\n\nPengajuan duplikat atau bulan tanggal GL tidak sama dengan bulan pengajuan:\n\n"
        + _table(profile["application_groups"][
            profile["application_groups"].get("duplikat", pd.Series(dtype=bool)).fillna(False)
            | profile["application_groups"].get("baris_bulan_tidak_cocok", pd.Series(dtype=str)).fillna("").ne("")
        ]),
        "## Keputusan perlu dikonfirmasi\n\n"
        "- Periksa baris berstatus ambiguous pada kandidat frasa serta pengajuan duplikat/bulan yang tidak cocok.\n"
        "- Konfirmasi apakah debit koreksi 40.000 pada KK/HO/2604/0006 memang mengurangi realisasi P-SDT/I/071.\n"
        "- Rentang WP aktual adalah baris 8-22, berbeda dari acuan legacy Row 6-20; SPEC bagian 3 menyebut mulai baris 8.\n"
        "- Baris STYLING berjumlah 12, tetapi klasifikasi berbasis kolom menghasilkan 9 SETTLEMENT dan 3 REFUND; SPEC menyebut 9 NEW_ADVANCE, sehingga perlu klarifikasi data/SPEC.\n"
        "- Saldo GL tidak konsisten pada dua baris dengan voucher PMT2/BK/2604/0037; verifikasi pemecahan jurnal atau saldo sumber.",
    ]
    return "\n\n".join(summary_sections)


def main() -> None:
    """Load source workbooks, write full profile, and print a compact summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gl", type=Path, default=GL_PATH)
    parser.add_argument("--working-paper", type=Path, default=WORKING_PAPER_PATH)
    parser.add_argument("--output-dir", type=Path, default=PROFILE_DIR)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    gl = load_gl(args.gl)
    wp, meta = load_working_paper(args.working_paper)
    profile = build_profile(gl, wp, meta)
    write_profile(profile, args.output_dir, args.report)
    print(_console_summary(profile))


if __name__ == "__main__":
    main()