from __future__ import annotations

import argparse
import csv
import importlib.util
import logging
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.config import GL_PATH, ROOT_DIR, UNIT_PATTERN, WORKING_PAPER_PATH
from src.loaders import load_gl, load_working_paper
from src.matcher import build_targets
from src.parsing import classify_gl_rows, extract_po_codes
from src.scoring import normalize_for_matching, score

logger = logging.getLogger(__name__)

LABEL_PATH = ROOT_DIR / "tests" / "golden" / "labels.csv"
REPORT_PATH = ROOT_DIR / "docs" / "TUNING_REPORT.md"
THRESHOLDS = tuple(round(0.40 + step * 0.05, 2) for step in range(10))
MARGINS = (0.05, 0.10, 0.15, 0.20)
BASE_METHODS = ("token_jaccard", "rapidfuzz_token_set", "rapidfuzz_partial", "tfidf_cosine")
WEIGHT_SETS: dict[str, dict[str, float]] = {
    "combined_balanced": {
        "token_jaccard": 0.25,
        "rapidfuzz_token_set": 0.25,
        "rapidfuzz_partial": 0.25,
        "tfidf_cosine": 0.25,
    },
    "combined_token_heavy": {
        "token_jaccard": 0.55,
        "rapidfuzz_token_set": 0.20,
        "rapidfuzz_partial": 0.10,
        "tfidf_cosine": 0.15,
    },
    "combined_fuzzy_heavy": {
        "token_jaccard": 0.15,
        "rapidfuzz_token_set": 0.35,
        "rapidfuzz_partial": 0.35,
        "tfidf_cosine": 0.15,
    },
}
UNIT_RE = re.compile(UNIT_PATTERN, re.IGNORECASE)
EXPECTED_TARGET_RE = re.compile(
    r"^(?:WP-\d+|NEW-[A-Z0-9]{2,}/(?:PO|WO|SPK|PGJ)/\d+|NONE)$",
    re.IGNORECASE,
)


def _unit_numbers(text: Any) -> set[str]:
    normalized = normalize_for_matching(text)
    return {value.upper() for value in UNIT_RE.findall(normalized)}


def _tfidf_pair(left: str, right: str) -> float:
    left_tokens = Counter(normalize_for_matching(left).split())
    right_tokens = Counter(normalize_for_matching(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    document_frequency = {
        token: int(token in left_tokens) + int(token in right_tokens)
        for token in left_tokens.keys() | right_tokens.keys()
    }
    idf = {token: math.log(3 / (1 + count)) + 1 for token, count in document_frequency.items()}
    left_vector = {token: count * idf[token] for token, count in left_tokens.items()}
    right_vector = {token: count * idf[token] for token, count in right_tokens.items()}
    dot = sum(left_vector[token] * right_vector[token] for token in left_vector.keys() & right_vector.keys())
    left_norm = math.sqrt(sum(value * value for value in left_vector.values()))
    right_norm = math.sqrt(sum(value * value for value in right_vector.values()))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def score_phrase(gl_description: Any, target_description: Any, method: str) -> float:
    """Score a phrase while rejecting candidates with conflicting unit numbers."""
    gl_units = _unit_numbers(gl_description)
    target_units = _unit_numbers(target_description)
    if gl_units and target_units and gl_units != target_units:
        return 0.0

    if method in WEIGHT_SETS:
        weights = WEIGHT_SETS[method]
        return sum(
            weight * score(gl_description, target_description, {"scorer": feature})
            for feature, weight in weights.items()
        )
    if method == "tfidf_cosine":
        value = _tfidf_pair(str(gl_description or ""), str(target_description or ""))
    elif method in BASE_METHODS:
        if method.startswith("rapidfuzz") and importlib.util.find_spec("rapidfuzz") is None:
            value = score(gl_description, target_description, {"scorer": "token_jaccard"})
        else:
            value = score(gl_description, target_description, {"scorer": method})
    else:
        raise ValueError(f"Unknown scoring method: {method}")
    return max(0.0, min(1.0, float(value)))


def rank_phrase_candidates(
    gl_description: Any,
    targets: list[dict[str, Any]],
    pengajuan_month: int | None,
    method: str,
) -> list[dict[str, Any]]:
    """Rank deterministically, applying the application-month filter first."""
    candidates: list[dict[str, Any]] = []
    for target in targets:
        target_date = pd.to_datetime(target.get("date"), errors="coerce")
        if pengajuan_month is not None and not pd.isna(pengajuan_month):
            if pd.isna(target_date) or int(target_date.month) != int(pengajuan_month):
                continue
        candidates.append(
            {
                "target_id": str(target.get("target_id")),
                "description": str(target.get("description") or ""),
                "score": score_phrase(gl_description, target.get("description"), method),
            }
        )
    return sorted(candidates, key=lambda item: (-item["score"], item["target_id"]))


def predict_target(
    candidates: list[dict[str, Any]], threshold: float, margin: float
) -> tuple[str | None, str]:
    if not candidates:
        return None, "month_mismatch_or_no_candidate"
    best = candidates[0]
    second_score = candidates[1]["score"] if len(candidates) > 1 else 0.0
    score_margin = best["score"] - second_score
    if best["score"] < threshold:
        return None, "below_threshold"
    if score_margin < margin:
        return None, "ambiguous"
    return best["target_id"], "matched"


def evaluate_predictions(rows: list[dict[str, Any]]) -> dict[str, int | float]:
    """Compute exact-target precision/recall counts, including true negatives."""
    correct = wrong = missed = true_none = positive_count = 0
    for row in rows:
        expected = str(row["expected_target"]).upper()
        predicted = row.get("predicted_target")
        predicted = None if predicted in (None, "") else str(predicted).upper()
        if expected == "NONE":
            if predicted is None:
                true_none += 1
            else:
                wrong += 1
            continue
        positive_count += 1
        if predicted is None:
            missed += 1
        elif predicted == expected:
            correct += 1
        else:
            wrong += 1
    precision = correct / (correct + wrong) if correct + wrong else 0.0
    recall = correct / positive_count if positive_count else 0.0
    return {
        "correct": correct,
        "wrong": wrong,
        "missed": missed,
        "true_none": true_none,
        "precision": precision,
        "recall": recall,
    }


def _configuration_grid() -> list[dict[str, Any]]:
    methods = [*BASE_METHODS, *WEIGHT_SETS]
    return [
        {"method": method, "threshold": threshold, "margin": margin}
        for method in methods
        for threshold in THRESHOLDS
        for margin in MARGINS
    ]


def _predict_rows(
    prepared: list[dict[str, Any]], configuration: dict[str, Any]
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in prepared:
        candidates = row["rankings"][configuration["method"]]
        predicted, reason = predict_target(
            candidates, configuration["threshold"], configuration["margin"]
        )
        output.append(
            {
                "expected_target": row["expected_target"],
                "predicted_target": predicted,
                "reason": reason,
                "label": row,
            }
        )
    return output


def _evaluate_configuration(
    prepared: list[dict[str, Any]], configuration: dict[str, Any]
) -> dict[str, Any]:
    predictions = _predict_rows(prepared, configuration)
    return {**configuration, **evaluate_predictions(predictions), "predictions": predictions}


def _complexity(method: str) -> int:
    if method in BASE_METHODS:
        return 1
    return len(WEIGHT_SETS[method])


def _result_order(result: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -float(result["precision"]),
        -float(result["recall"]),
        _complexity(result["method"]),
        result["method"],
        -float(result["threshold"]),
        -float(result["margin"]),
    )


def _prepare_labels(
    labels: pd.DataFrame,
    gl: pd.DataFrame,
    targets: pd.DataFrame,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    target_records = targets.to_dict(orient="records")
    prepared: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for label_index, label in labels.iterrows():
        expected = str(label.get("expected_target", "")).strip().upper()
        voucher = str(label.get("voucher_no", "")).strip()
        if not EXPECTED_TARGET_RE.fullmatch(expected):
            excluded.append({"voucher_no": voucher, "reason": f"unsupported expected_target: {expected}"})
            continue

        if "gl_row" in labels.columns and pd.notna(label.get("gl_row")):
            matching_gl = gl[gl["gl_row"].astype(str) == str(label["gl_row"]).strip()]
        else:
            matching_gl = gl[gl["voucher_no"].astype(str).str.strip() == voucher]
        if len(matching_gl) != 1:
            excluded.append({"voucher_no": voucher, "reason": f"expected one GL row, found {len(matching_gl)}"})
            continue
        gl_row = matching_gl.iloc[0]
        po_codes = gl_row.get("po_codes", [])
        if not isinstance(po_codes, list) or po_codes:
            excluded.append({"voucher_no": voucher, "reason": "phrase matching applies only to rows without PO codes"})
            continue
        if expected != "NONE" and not any(target["target_id"].upper() == expected for target in target_records):
            excluded.append({"voucher_no": voucher, "reason": f"expected target not present: {expected}"})
            continue

        rankings = {
            method: rank_phrase_candidates(
                gl_row.get("description"),
                target_records,
                gl_row.get("pengajuan_month"),
                method,
            )
            for method in [*BASE_METHODS, *WEIGHT_SETS]
        }
        prepared.append(
            {
                "label_index": int(label_index),
                "voucher_no": voucher,
                "gl_row": gl_row.to_dict(),
                "expected_target": expected,
                "note": str(label.get("note", "")),
                "rankings": rankings,
            }
        )
    return prepared, excluded


def _sweep(prepared: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [_evaluate_configuration(prepared, config) for config in _configuration_grid()],
        key=_result_order,
    )


def _loo_changes(prepared: list[dict[str, Any]], selected: dict[str, Any]) -> tuple[int, int]:
    changed = 0
    total = len(prepared)
    for index in range(total):
        reduced = prepared[:index] + prepared[index + 1 :]
        candidates = _sweep(reduced)
        perfect = [candidate for candidate in candidates if candidate["precision"] == 1.0]
        winner = perfect[0] if perfect else candidates[0]
        if any(winner[key] != selected[key] for key in ("method", "threshold", "margin")):
            changed += 1
    return changed, total


def _top_feature_scores(label: dict[str, Any], candidates: list[dict[str, Any]]) -> str:
    feature_names = [*BASE_METHODS, *WEIGHT_SETS]
    rows: list[str] = []
    for candidate in candidates[:3]:
        features = ", ".join(
            f"{feature}={score_phrase(label['gl_row'].get('description'), candidate['description'], feature):.3f}"
            for feature in feature_names
        )
        rows.append(f"{candidate['target_id']} ({candidate['score']:.3f}; {features})")
    return "; ".join(rows) if rows else "(tidak ada kandidat setelah filter bulan)"


def _md_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    header = "| " + " | ".join(label for label, _ in columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(str(row.get(key, "")).replace("|", "\\|") for _, key in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, divider, *body])


def _stability_note(results: list[dict[str, Any]], selected: dict[str, Any]) -> str:
    neighbors = [
        item
        for item in results
        if item["method"] == selected["method"]
        and item["margin"] == selected["margin"]
        and round(abs(item["threshold"] - selected["threshold"]), 2) == 0.05
    ]
    if not neighbors:
        return "Tidak ada tetangga threshold yang dapat dibandingkan."
    if all(item["precision"] >= selected["precision"] for item in neighbors):
        return "Daerah datar: presisi tidak turun pada tetangga threshold yang tersedia."
    return "Titik tajam: presisi turun pada setidaknya satu tetangga threshold."


def _build_report(
    labels_count: int,
    positives: int,
    negatives: int,
    prepared: list[dict[str, Any]],
    excluded: list[dict[str, str]],
    results: list[dict[str, Any]],
) -> str:
    perfect = [item for item in results if item["precision"] == 1.0]
    selected = perfect[0] if perfect else None
    top_five = results[:5]
    top_table = _md_table(
        top_five,
        [
            ("Method", "method"),
            ("Threshold", "threshold"),
            ("Margin", "margin"),
            ("Correct", "correct"),
            ("Wrong", "wrong"),
            ("Missed", "missed"),
            ("True NONE", "true_none"),
            ("Precision", "precision"),
            ("Recall", "recall"),
        ],
    )
    if selected is None:
        recommendation = "Tidak ada konfigurasi dengan presisi 1.0; tidak ada rekomendasi aman."
        stability = "Tidak dinilai karena tidak ada konfigurasi berpresisi 1.0."
        loo = "Tidak dinilai karena tidak ada konfigurasi berpresisi 1.0."
        details: list[str] = []
    else:
        recommendation = (
            f"`{selected['method']}`, threshold `{selected['threshold']:.2f}`, margin "
            f"`{selected['margin']:.2f}` (precision `{selected['precision']:.3f}`, "
            f"recall `{selected['recall']:.3f}`). Ini rekomendasi eksperimen saja; "
            "belum diterapkan ke matcher/config."
        )
        stability = _stability_note(results, selected)
        changed, total = _loo_changes(prepared, selected)
        loo = f"Pilihan berubah pada {changed}/{total} iterasi leave-one-out."
        details = []
        for prediction in selected["predictions"]:
            if prediction["reason"] == "matched" and prediction["predicted_target"] == prediction["expected_target"]:
                continue
            label = prediction["label"]
            candidates = label["rankings"][selected["method"]]
            description = str(label["gl_row"].get("description", "")).replace("|", "\\|")
            details.append(
                f"- `{label['voucher_no']}` expected `{label['expected_target']}`, got "
                f"`{prediction['predicted_target']}` ({prediction['reason']}); GL: {description}; "
                f"top candidates: {_top_feature_scores(label, candidates)}"
            )
    excluded_text = "\n".join(
        f"- `{row['voucher_no']}`: {row['reason']}" for row in excluded
    ) or "- Tidak ada."
    details_text = "\n".join(details) or "- Tidak ada kesalahan atau baris terlewat."
    return f"""# Phrase Matching Tuning Report

## Data Labels

- Baris berlabel: {labels_count}
- Positif valid: {positives}
- Negatif valid (`NONE`): {negatives}
- Baris yang dapat dievaluasi (phrase, tanpa PO): {len(prepared)}
- Label dikecualikan: {len(excluded)}

Baris berlabel yang dikecualikan tidak diubah. `NEW-ANY` tidak sesuai format target pada prompt (`NEW-<kode PO>`), dan label PBB yang bertanda perlu verifikasi tetap dianggap sebagai label manual bila formatnya valid.

{excluded_text}

## Top Configurations

{top_table}

## Recommendation

{recommendation}

Stability: {stability}

Leave-one-out: {loo}

## Remaining Errors and Misses

{details_text}

## Limitations

- Sampel valid hanya {len(prepared)} dari {labels_count} label; {negatives} label negatif, sehingga false-positive behavior kurang teruji.
- Label bertanda `PERLU VERIFIKASI` belum dikonfirmasi ulang; hasil tuning tidak mengesahkan kebenaran label.
- Skor fuzzy memakai RapidFuzz bila tersedia; tanpa paket tersebut, dua metode fuzzy memakai token Jaccard sebagai fallback dan hasilnya tidak independen.
- Tidak ada embedding yang dijalankan kecuali diminta secara eksplisit; eksperimen ini tidak mengunduh model atau memanggil API.
- Pemilihan konfigurasi pada dataset kecil berisiko overfit. Rekomendasi tidak diterapkan otomatis.
"""


def run_tuning(
    label_path: Path = LABEL_PATH,
    with_embeddings: bool = False,
) -> tuple[str, list[dict[str, Any]], list[dict[str, str]]]:
    if not label_path.exists():
        raise ValueError(f"Golden labels not found: {label_path}")
    labels = pd.read_csv(label_path, dtype=str).fillna("")
    if len(labels) < 8:
        raise ValueError(f"At least 8 labeled rows are required; found {len(labels)}")
    if not {"expected_target"}.issubset(labels.columns) or not ({"gl_row", "voucher_no"} & set(labels.columns)):
        raise ValueError("Labels must contain expected_target and gl_row or voucher_no")
    if not GL_PATH.exists() or not WORKING_PAPER_PATH.exists():
        raise ValueError("Original GL and Working Paper workbooks are required for tuning")

    gl = load_gl(GL_PATH)
    wp, _ = load_working_paper(WORKING_PAPER_PATH)
    wp["po_codes"] = wp["description"].map(extract_po_codes)
    wp_po_codes = {code for codes in wp["po_codes"] for code in codes}
    gl = classify_gl_rows(gl, wp_po_codes)
    targets, _ = build_targets(wp, gl)
    prepared, excluded = _prepare_labels(labels, gl, targets)
    valid_expected = [
        str(value).upper()
        for value in labels["expected_target"]
        if EXPECTED_TARGET_RE.fullmatch(str(value).strip())
    ]
    positives = sum(target != "NONE" for target in valid_expected)
    negatives = sum(target == "NONE" for target in valid_expected)
    logger.info(
        "Labeled rows=%d; positive=%d; negative=%d; phrase eligible=%d; excluded=%d",
        len(labels),
        positives,
        negatives,
        len(prepared),
        len(excluded),
    )
    if with_embeddings:
        if importlib.util.find_spec("sentence_transformers") is None:
            excluded.append({"voucher_no": "", "reason": "embedding skipped: sentence-transformers is not installed"})
        else:
            excluded.append({"voucher_no": "", "reason": "embedding skipped: no verified local model was selected"})
    results = _sweep(prepared)
    report = _build_report(len(labels), positives, negatives, prepared, excluded, results)
    return report, results, excluded


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare deterministic phrase matching strategies.")
    parser.add_argument("--with-embeddings", action="store_true", help="Check local embedding availability; never downloads a model")
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        report, results, excluded = run_tuning(with_embeddings=arguments.with_embeddings)
    except ValueError as error:
        logger.error("%s", error)
        return 2
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"Report: {REPORT_PATH.relative_to(ROOT_DIR)}")
    print("Top 5 configurations:")
    for item in results[:5]:
        print(
            f"  {item['method']} threshold={item['threshold']:.2f} margin={item['margin']:.2f} "
            f"precision={item['precision']:.3f} recall={item['recall']:.3f} "
            f"correct={item['correct']} wrong={item['wrong']} missed={item['missed']}"
        )
    print(f"Excluded labels/notes: {len(excluded)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())