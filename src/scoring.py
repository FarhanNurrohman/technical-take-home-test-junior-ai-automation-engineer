from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Iterable

from src.config import PHRASE_SCORER, PHRASE_THRESHOLDS, PHRASE_WEIGHTS, UNIT_PATTERN

_UNIT_RE = re.compile(UNIT_PATTERN, re.IGNORECASE)


def _as_tokens(text: Any) -> list[str]:
    if text is None:
        return []
    cleaned = str(text).lower()
    cleaned = re.sub(r"\([^)]*\)", " ", cleaned)
    cleaned = re.sub(r"[\W_]+", " ", cleaned)
    return [token for token in cleaned.split() if token]


def normalize_for_matching(text: Any) -> str:
    """Collapse noisy descriptions into a comparable phrase form."""
    if text is None:
        return ""
    lowered = str(text).lower()
    lowered = re.sub(r"\([^)]*\)", " ", lowered)
    lowered = lowered.replace("-", " ")
    lowered = re.sub(r"[.,;:/]", " ", lowered)
    lowered = re.sub(r"\b(?:pengembalian|kelebihan|dana|um|advance|uang|muka|transfer|kekurangan|settlement|realisasi|pelunasan|no|nomor|voucher|umum|show|unit|apartement|apartment|pembayaran|kartu|kredit|untuk|tagihan|periode)\b", " ", lowered)
    lowered = re.sub(r"\b(?:p-sdt|bca2|pmt2|kk|ho|bk|bm|adv|fr01|hljc|tp01)\b", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    tokens: list[str] = []
    for token in re.findall(r"\d+|[a-z]+", lowered):
        if token in {"pengembalian", "kelebihan", "dana", "um", "advance", "uang", "muka", "transfer", "kekurangan", "settlement", "realisasi", "pelunasan", "no", "nomor", "voucher", "unit", "studio", "bedroom", "bulan", "tahun", "show", "apartemen", "apartment", "the", "parc"}:
            continue
        if token in {"sm", "studio", "bedroom", "bulan", "tahun"}:
            tokens.append(token)
            continue
        if token.isdigit() or token.isalpha():
            tokens.append(token)
    return " ".join(tokens)


def _unit_numbers(text: Any) -> set[str]:
    if text is None:
        return set()
    return set(_UNIT_RE.findall(str(text)))


def _token_set_similarity(left: Iterable[str], right: Iterable[str]) -> float:
    left_tokens = set(left)
    right_tokens = set(right)
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = left_tokens & right_tokens
    return len(intersection) / len(left_tokens | right_tokens)


def _token_jaccard(left: str, right: str) -> float:
    left_tokens = set(_as_tokens(left))
    right_tokens = set(_as_tokens(right))
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _rapidfuzz_token_set(left: str, right: str) -> float:
    try:
        from rapidfuzz import fuzz
    except Exception:
        return _token_jaccard(left, right)
    if not left and not right:
        return 1.0
    score = fuzz.token_set_ratio(left, right) / 100.0
    return max(0.0, min(1.0, score))


def _rapidfuzz_partial(left: str, right: str) -> float:
    try:
        from rapidfuzz import fuzz
    except Exception:
        return _token_jaccard(left, right)
    if not left and not right:
        return 1.0
    score = fuzz.partial_ratio(left, right) / 100.0
    return max(0.0, min(1.0, score))


def _tfidf_cosine(left: str, right: str) -> float:
    left_tokens = Counter(_as_tokens(left))
    right_tokens = Counter(_as_tokens(right))
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left_tokens.values()))
    right_norm = math.sqrt(sum(value * value for value in right_tokens.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    dot = sum(left_tokens[token] * right_tokens[token] for token in left_tokens.keys() & right_tokens.keys())
    return dot / (left_norm * right_norm)


def _combined(left: str, right: str) -> float:
    weights = PHRASE_WEIGHTS or {"token_jaccard": 0.30, "rapidfuzz_token_set": 0.30, "rapidfuzz_partial": 0.20, "tfidf_cosine": 0.20}
    scores = {
        "token_jaccard": _token_jaccard(left, right),
        "rapidfuzz_token_set": _rapidfuzz_token_set(left, right),
        "rapidfuzz_partial": _rapidfuzz_partial(left, right),
        "tfidf_cosine": _tfidf_cosine(left, right),
    }
    total_weight = sum(weights.get(name, 0.0) for name in scores)
    if total_weight == 0:
        return 0.0
    return sum(weights.get(name, 0.0) * value for name, value in scores.items()) / total_weight


SCORERS: dict[str, Any] = {
    "token_jaccard": _token_jaccard,
    "rapidfuzz_token_set": _rapidfuzz_token_set,
    "rapidfuzz_partial": _rapidfuzz_partial,
    "tfidf_cosine": _tfidf_cosine,
    "combined": _combined,
}


def score(gl_text: Any, target_text: Any, context: Any | None = None) -> float:
    """Calculate a deterministic 0..1 phrase similarity score with unit veto handling."""
    left = normalize_for_matching(gl_text)
    right = normalize_for_matching(target_text)
    if left == right:
        return 1.0

    left_units = _unit_numbers(left)
    right_units = _unit_numbers(right)
    if left_units and right_units and left_units != right_units:
        return 0.0

    scorer_name = (context or {}).get("scorer") if isinstance(context, dict) else PHRASE_SCORER
    if scorer_name is None:
        scorer_name = PHRASE_SCORER
    scorer = SCORERS.get(str(scorer_name), _token_jaccard)
    value = float(scorer(left, right))
    if not math.isfinite(value):
        return 0.0
    return max(0.0, min(1.0, value))


def phrase_threshold_for(scorer_name: str) -> float:
    threshold_map = PHRASE_THRESHOLDS or {}
    return float(threshold_map.get(scorer_name, threshold_map.get("default", 0.6)))
