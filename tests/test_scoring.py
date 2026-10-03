from src.scoring import score


def test_score_is_deterministic_and_bounded():
    assert 0.0 <= score("STYLING APARTEMEN THE PARC SM 1132", "STYLING APARTEMEN THE PARC SM 1127", {}) <= 1.0
    assert score("same text", "same text", {}) == 1.0
    assert score("alpha beta", "alpha beta", {}) == 1.0
    assert score("alpha beta", "gamma delta", {}) < 1.0


def test_score_vetoes_different_unit_numbers_before_threshold():
    text_a = "STYLING APARTEMEN THE PARC SM 1132 (2 BEDROOM)"
    text_b = "STYLING APARTEMEN THE PARC SM 1127 (STUDIO)"
    assert score(text_a, text_b, {}) == 0.0
