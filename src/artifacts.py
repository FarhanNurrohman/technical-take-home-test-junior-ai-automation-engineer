"""Versioned JSON persistence for pipeline outputs used by the chat assistant."""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

SCHEMA_VERSION = 1


def _encode(value: Any) -> Any:
    if value is pd.NaT:
        return {"__type__": "nat"}
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return {"__type__": "datetime", "value": value.isoformat()}
    if value is None:
        return None
    if isinstance(value, (float,)) and not math.isfinite(value):
        return {"__type__": "nan"}
    if hasattr(value, "item"):
        return _encode(value.item())
    if isinstance(value, dict):
        return {str(key): _encode(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(child) for child in value]
    if isinstance(value, (str, int, float, bool)):
        return value
    if pd.isna(value):
        return None
    raise TypeError(f"Unsupported artifact value type: {type(value).__name__}")


def _decode(value: Any) -> Any:
    if isinstance(value, dict):
        marker = value.get("__type__")
        if marker == "datetime":
            return pd.Timestamp(value["value"])
        if marker == "nat":
            return pd.NaT
        if marker == "nan":
            return float("nan")
        return {key: _decode(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_decode(child) for child in value]
    return value


def _encode_frame(frame: pd.DataFrame) -> dict[str, Any]:
    return {
        "columns": list(frame.columns),
        "dtypes": {column: str(dtype) for column, dtype in frame.dtypes.items()},
        "records": [
            {column: _encode(value) for column, value in record.items()}
            for record in frame.to_dict(orient="records")
        ],
    }


def _decode_frame(payload: Any, label: str) -> pd.DataFrame:
    if not isinstance(payload, dict) or not isinstance(payload.get("columns"), list) or not isinstance(payload.get("records"), list):
        raise ValueError(f"Invalid {label} dataframe in artifacts: expected columns and records.")
    columns = payload["columns"]
    if not all(isinstance(column, str) for column in columns) or len(set(columns)) != len(columns):
        raise ValueError(f"Invalid {label} dataframe in artifacts: columns must be unique strings.")
    records = payload["records"]
    if not all(isinstance(row, dict) and set(row).issubset(columns) for row in records):
        raise ValueError(f"Invalid {label} dataframe records in artifacts: each record must map declared columns.")
    if not isinstance(payload.get("dtypes", {}), dict):
        raise ValueError(f"Invalid {label} dataframe in artifacts: dtypes must be an object.")
    rows = [{key: _decode(value) for key, value in row.items()} for row in records]
    frame = pd.DataFrame(rows, columns=columns)
    for column, dtype in payload.get("dtypes", {}).items():
        if column not in frame.columns:
            continue
        try:
            if dtype.startswith("datetime64"):
                frame[column] = pd.to_datetime(frame[column], errors="coerce")
            elif dtype in {"float64", "float32"}:
                frame[column] = frame[column].astype(dtype)
            elif dtype in {"int64", "int32", "bool"} and not frame[column].isna().any():
                frame[column] = frame[column].astype(dtype)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError(f"Invalid values for {label}.{column} in artifacts.") from error
    return frame


def _read(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Artifact {path.name} tidak ditemukan di {path.parent}; jalankan main.py terlebih dahulu.")
    try:
        with path.open("r", encoding="utf-8") as source:
            payload = json.load(source)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Artifact {path.name} tidak dapat dibaca sebagai JSON valid.") from error
    if not isinstance(payload, dict):
        raise ValueError(f"Schema artifact {path.name} tidak valid.")
    version = payload.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema for {path.name}: version {version!r}; application version is {SCHEMA_VERSION}.")
    return payload


def save_artifacts(artifacts: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    """Write validated result and unmatched JSON artifacts without network access."""
    required = {"df_result", "metrics", "reconcile_result"}
    missing = required.difference(artifacts)
    if missing:
        raise ValueError(f"Missing required artifact fields: {', '.join(sorted(missing))}")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    result_path = output / "result.json"
    unmatched_path = output / "unmatched.json"
    result_payload = {
        "schema_version": SCHEMA_VERSION,
        "df_result": _encode_frame(artifacts["df_result"]),
        "metrics": _encode(artifacts["metrics"]),
        "reconcile_result": _encode(artifacts["reconcile_result"]),
    }
    unmatched = artifacts.get("df_unmatched", pd.DataFrame())
    unmatched_payload = {"schema_version": SCHEMA_VERSION, "df_unmatched": _encode_frame(unmatched)}
    for path, payload in ((result_path, result_payload), (unmatched_path, unmatched_payload)):
        path.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
    return {"result": str(result_path), "unmatched": str(unmatched_path)}


def load_artifacts(output_dir: str | Path) -> dict[str, Any]:
    """Load and validate the versioned result and unmatched artifacts."""
    output = Path(output_dir)
    result_payload = _read(output / "result.json", "result")
    unmatched_payload = _read(output / "unmatched.json", "unmatched")
    if not {"df_result", "metrics", "reconcile_result"}.issubset(result_payload):
        raise ValueError("Schema artifact result.json tidak lengkap.")
    if "df_unmatched" not in unmatched_payload:
        raise ValueError("Schema artifact unmatched.json tidak lengkap.")
    if not isinstance(result_payload["metrics"], dict) or not isinstance(result_payload["reconcile_result"], dict):
        raise ValueError("Schema artifact result.json tidak valid: metrics dan reconcile_result harus berupa object.")
    return {
        "df_result": _decode_frame(result_payload["df_result"], "df_result"),
        "metrics": _decode(result_payload["metrics"]),
        "reconcile_result": _decode(result_payload["reconcile_result"]),
        "df_unmatched": _decode_frame(unmatched_payload["df_unmatched"], "df_unmatched"),
    }