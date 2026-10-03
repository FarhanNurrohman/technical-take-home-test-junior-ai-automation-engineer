import pytest

from scripts.tune_matching import (
    evaluate_predictions,
    rank_phrase_candidates,
    score_phrase,
)


def test_evaluate_predictions_counts_correct_wrong_missed_and_true_none():
    metrics = evaluate_predictions(
        [
            {"expected_target": "WP-1", "predicted_target": "WP-1"},
            {"expected_target": "WP-2", "predicted_target": None},
            {"expected_target": "WP-3", "predicted_target": "WP-4"},
            {"expected_target": "NONE", "predicted_target": None},
            {"expected_target": "NONE", "predicted_target": "WP-1"},
        ]
    )

    assert metrics == {
        "correct": 1,
        "wrong": 2,
        "missed": 1,
        "true_none": 1,
        "precision": pytest.approx(1 / 3),
        "recall": pytest.approx(1 / 3),
    }


@pytest.mark.parametrize(
    "method",
    [
        "token_jaccard",
        "rapidfuzz_token_set",
        "rapidfuzz_partial",
        "tfidf_cosine",
        "combined_balanced",
        "combined_token_heavy",
        "combined_fuzzy_heavy",
    ],
)
def test_unit_number_veto_applies_to_every_method(method):
    score = score_phrase(
        "STYLING SHOW UNIT THE PARC SM 1132",
        "STYLING SHOW UNIT THE PARC SM 1127",
        method,
    )

    assert score == 0


def test_candidate_ranking_is_deterministic():
    description = "PENGEMBALIAN UM SHOW UNIT THE PARC BULAN MARET 2026"
    targets = [
        {"target_id": "WP-2", "date": "2026-03-01", "description": "SHOW UNIT THE PARC MARET 2026"},
        {"target_id": "WP-1", "date": "2026-03-01", "description": "SHOW UNIT THE PARC MARET 2026"},
    ]

    first = rank_phrase_candidates(description, targets, 3, "token_jaccard")
    second = rank_phrase_candidates(description, targets, 3, "token_jaccard")

    assert first == second
    assert [candidate["target_id"] for candidate in first] == ["WP-1", "WP-2"]