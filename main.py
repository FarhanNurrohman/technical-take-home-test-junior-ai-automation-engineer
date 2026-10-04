"""Command-line orchestration for SouthCity settlement automation."""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path
from typing import Any

import pandas as pd

from app import launch_chat
from src.ai_summary import compute_metrics, fallback_summary, generate_executive_summary
from src.artifacts import save_artifacts
from src.config import GL_PATH, ROOT_DIR, WORKING_PAPER_PATH
from src.loaders import check_gl_balance_integrity, load_gl, load_working_paper
from src.matcher import (
    aggregate_realizations,
    build_targets,
    match_gl_to_targets,
    reconcile,
    suggest_settlement_candidates,
    summarize_sections,
)
from src.parsing import classify_gl_rows, extract_po_codes
from src.sheets_exporter import export_to_sheets, export_to_xlsx

logger = logging.getLogger(__name__)


def _stage(name: str, started: float, rows: int | None = None) -> None:
    detail = f", rows={rows}" if rows is not None else ""
    logger.info("Stage %s complete%s, duration=%.3fs", name, detail, time.perf_counter() - started)


def run_pipeline(
    gl_path: str | Path = GL_PATH,
    wp_path: str | Path = WORKING_PAPER_PATH,
    output_dir: str | Path = ROOT_DIR / "output",
    *,
    dry_run: bool = False,
    no_ai: bool = False,
) -> dict[str, Any]:
    """Load, match, reconcile, summarize, persist, and optionally export results."""
    started = time.perf_counter()
    gl = load_gl(gl_path)
    wp, wp_meta = load_working_paper(wp_path)
    _stage("load", started, len(gl) + len(wp))
    logger.info("Working Paper data rows detected: %d-%d", wp_meta.get("first_row", 0), wp_meta.get("last_row", 0))

    started = time.perf_counter()
    wp = wp.copy()
    wp["po_codes"] = wp["description"].map(extract_po_codes)
    wp_po_codes = {code for codes in wp["po_codes"] for code in codes}
    classified_gl = classify_gl_rows(gl, wp_po_codes)
    integrity = check_gl_balance_integrity(classified_gl)
    logger.info("GL running-balance integrity exceptions: %d", len(integrity))
    targets, debit_exceptions = build_targets(wp, classified_gl)
    matches, unmatched = match_gl_to_targets(classified_gl, targets)
    _stage("match", started, len(matches))

    started = time.perf_counter()
    df_result = aggregate_realizations(targets, matches, classified_gl)
    section_summary = summarize_sections(df_result)
    _stage("aggregate", started, len(df_result))

    started = time.perf_counter()
    reconcile_result = reconcile(classified_gl, matches, unmatched, targets)
    reconcile_result["reconcile_diff"] = reconcile_result["diff_total"]
    reconcile_result["reconcile_ok"] = abs(float(reconcile_result["diff_total"])) <= 0.01
    logger.info(
        "Reconciliation: GL credit=%.2f, matched=%.2f, unmatched=%.2f, difference=%.2f",
        reconcile_result["total_credit_gl"],
        reconcile_result["matched_credit_gl"],
        reconcile_result["unmatched_credit_gl"],
        reconcile_result["diff_total"],
    )
    _stage("reconcile", started, len(unmatched))

    started = time.perf_counter()
    suggestions = suggest_settlement_candidates(df_result, classified_gl, unmatched)
    metrics = compute_metrics(df_result, reconcile_result, unmatched)
    if dry_run or no_ai:
        summary_text = fallback_summary(metrics)
    else:
        summary_text = generate_executive_summary(df_result, reconcile_result, unmatched)
    _stage("summary", started, len(metrics.get("unsettled_items", [])))

    artifacts = {
        "df_result": df_result,
        "metrics": metrics,
        "reconcile_result": reconcile_result,
        "df_unmatched": unmatched,
    }
    save_artifacts(artifacts, output_dir)
    started = time.perf_counter()
    if dry_run:
        export_details = export_to_xlsx(
            df_result,
            summary_text,
            metrics,
            unmatched,
            df_debit_exceptions=debit_exceptions,
            df_suggestions=suggestions,
            path=Path(output_dir) / "result.xlsx",
            summarize_sections=summarize_sections,
        )
        logger.info("Dry run wrote %s", export_details["path"])
    else:
        export_details = export_to_sheets(
            df_result,
            summary_text,
            metrics,
            unmatched,
            df_debit_exceptions=debit_exceptions,
            df_suggestions=suggestions,
            summarize_sections=summarize_sections,
        )
    _stage("export", started, len(df_result))
    return {
        **artifacts,
        "summary_text": summary_text,
        "integrity_exceptions": integrity,
        "debit_exceptions": debit_exceptions,
        "suggestions": suggestions,
        "section_summary": section_summary,
        "export_details": export_details,
    }


def main() -> int:
    """Run the CLI pipeline and return a process exit code."""
    parser = argparse.ArgumentParser(description="SouthCity advance settlement pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Write output/result.xlsx without Gemini or Google Sheets")
    parser.add_argument("--no-ai", action="store_true", help="Use deterministic summary instead of Gemini")
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        result = run_pipeline(dry_run=arguments.dry_run, no_ai=arguments.no_ai)
    except Exception:
        logger.exception("Settlement pipeline failed")
        return 1

    metrics = result["metrics"]
    print(
        "Ringkasan: "
        f"advance awal={metrics['wp']['total_advance']:.2f}; "
        f"realisasi WP={metrics['wp']['total_realization']:.2f}; "
        f"kredit GL unmatched={metrics['unmatched_count']} baris / {metrics['unmatched_total']:.2f}; "
        f"selisih rekonsiliasi={result['reconcile_result']['diff_total']:.2f}"
    )
    launch_chat(
        result,
        use_ai=not arguments.no_ai,
        data_status="Data pipeline settlement (snapshot saat pipeline selesai)",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())