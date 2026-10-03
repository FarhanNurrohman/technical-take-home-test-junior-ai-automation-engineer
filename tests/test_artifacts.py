from __future__ import annotations

import pandas as pd
import pytest

from src.artifacts import load_artifacts, save_artifacts


def test_artifact_dataframe_round_trip_preserves_timestamps_and_missing_values(tmp_path, chat_artifacts):
    chat_artifacts["df_result"].loc[0, "realization_date"] = pd.Timestamp("2026-04-17")
    chat_artifacts["df_result"].loc[1, "realization_date"] = pd.NaT

    save_artifacts(chat_artifacts, tmp_path)
    restored = load_artifacts(tmp_path)

    pd.testing.assert_frame_equal(restored["df_result"], chat_artifacts["df_result"], check_dtype=False)
    assert restored["reconcile_result"] == chat_artifacts["reconcile_result"]


def test_load_artifacts_explains_missing_result_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="result.json"):
        load_artifacts(tmp_path)


def test_load_artifacts_rejects_unsupported_schema_version(tmp_path):
    (tmp_path / "result.json").write_text('{"schema_version": 0}', encoding="utf-8")

    with pytest.raises(ValueError, match="schema"):
        load_artifacts(tmp_path)


def test_load_artifacts_rejects_malformed_dataframe_records(tmp_path):
    (tmp_path / "result.json").write_text(
        '{"schema_version": 1, "df_result": {"columns": ["target_id"], '
        '"records": [["not-a-record"]], "dtypes": {}}, "metrics": {}, '
        '"reconcile_result": {}}',
        encoding="utf-8",
    )
    (tmp_path / "unmatched.json").write_text(
        '{"schema_version": 1, "df_unmatched": {"columns": [], "records": [], "dtypes": {}}}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="records"):
        load_artifacts(tmp_path)