import pytest

from src.config import GL_PATH, WORKING_PAPER_PATH
from src.loaders import load_gl, load_working_paper
from src.matcher import aggregate_realizations, build_targets, match_gl_to_targets, reconcile
from src.parsing import classify_gl_rows, extract_po_codes


@pytest.mark.skipif(
    not GL_PATH.exists() or not WORKING_PAPER_PATH.exists(),
    reason="source workbooks unavailable",
)
def test_verified_styling_rows_match_golden_expectations():
    gl = load_gl(GL_PATH)
    wp, _ = load_working_paper(WORKING_PAPER_PATH)
    wp["po_codes"] = wp["description"].map(extract_po_codes)
    wp_po_codes = {code for codes in wp["po_codes"] for code in codes}
    gl = classify_gl_rows(gl, wp_po_codes)

    targets, _ = build_targets(wp, gl)
    matches, unmatched = match_gl_to_targets(gl, targets)
    result = aggregate_realizations(targets, matches, gl)
    summary = reconcile(gl, matches, unmatched, targets)
    original_wp = result[result["target_type"] == "WP"]
    styling = original_wp.set_index("wp_row").loc[[9, 10]]

    assert styling.loc[9, "realization_voucher_no"] == "PMT2/BM/2604/0007"
    assert styling.loc[9, "realization_amount"] == pytest.approx(2_028_300)
    assert styling.loc[9, "balance"] == pytest.approx(23_667_600)
    assert styling.loc[10, "realization_voucher_no"] == (
        "PMT2/BM/2604/0008, KK/HO/2604/0006 (koreksi)"
    )
    assert styling.loc[10, "realization_amount"] == pytest.approx(268_000)
    assert styling.loc[10, "balance"] == pytest.approx(1_315_700)
    assert styling["status"].tolist() == ["PARTIAL", "PARTIAL"]
    assert styling["need_settlement_evidence"].all()

    assert original_wp["amount"].sum() == pytest.approx(570_406_879)
    assert original_wp["realization_amount"].sum() == pytest.approx(119_797_300)
    assert original_wp["status"].isin(["UNSETTLED", "PARTIAL"]).sum() == 5
    assert summary["diff_total"] == 0