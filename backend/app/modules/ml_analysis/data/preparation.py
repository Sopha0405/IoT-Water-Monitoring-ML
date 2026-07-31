from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from app.modules.ml_analysis.data.io import read_dataframe, sha256_file, write_dataframe, write_json
from app.modules.ml_analysis.data.common import (
    SUSPICIOUS_UNKNOWN_STATUSES,
    TECHNICAL_STATUSES,
    add_interval_columns,
    normalize_reading_columns,
)


def prepare_dataset(input_path: str | Path, output_path: str | Path, report_path: str | Path) -> dict[str, Any]:
    source = Path(input_path)
    frame = add_interval_columns(normalize_reading_columns(read_dataframe(source)))
    original_rows = len(frame)
    reasons = {
        "invalid_timestamp": frame["timestamp"].isna(),
        "missing_sensor_id": frame["sensor_id"].isna() | frame["sensor_id"].astype(str).eq(""),
        "nan_flow": frame["flow_lpm"].isna(),
        "infinite_flow": np.isinf(frame["flow_lpm"].to_numpy(dtype=float, na_value=np.nan)),
        "negative_flow": frame["flow_lpm"].lt(0),
        "duplicate": frame["is_duplicate"],
        "irregular_interval": frame["is_irregular_interval"],
        "sensor_error": frame["status"].isin(TECHNICAL_STATUSES) | frame["is_sensor_error"].fillna(False),
        "maintenance": frame["status"].isin({"maintenance", "mantenimiento"}) | frame["is_maintenance"].fillna(False),
        "unknown_suspicious": frame["status"].isin(SUSPICIOUS_UNKNOWN_STATUSES) & frame["flow_lpm"].gt(0.50),
    }
    exclusion_mask = np.zeros(len(frame), dtype=bool)
    reason_counts: dict[str, int] = {}
    for reason, mask in reasons.items():
        mask_array = np.asarray(mask, dtype=bool)
        reason_counts[reason] = int(mask_array.sum())
        exclusion_mask |= mask_array

    clean = frame.loc[~exclusion_mask].copy()
    clean.sort_values(["sensor_id", "timestamp"], inplace=True)
    clean.reset_index(drop=True, inplace=True)
    clean["is_sensor_error"] = clean["is_sensor_error"].fillna(False).astype(bool)
    clean["is_normal_difficult"] = clean["is_normal_difficult"].fillna(False).astype(bool) | clean["label_status"].astype("string").str.contains("difficult|guard|clean|night|feriado|extended", case=False, na=False)
    write_dataframe(clean, output_path)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_path": str(source),
        "input_sha256": sha256_file(source),
        "output_path": str(output_path),
        "original_rows": int(original_rows),
        "clean_rows": int(len(clean)),
        "excluded_rows": int(original_rows - len(clean)),
        "exclusion_counts": reason_counts,
        "kept_anomaly_rows_for_evaluation": int(clean["actual_label"].eq(1).sum()),
        "kept_injected_anomaly_rows_for_evaluation": int(clean["is_injected_anomaly"].fillna(False).sum()),
        "preserved_for_evaluation_policy": [
            "anomalias",
            "normales_dificiles",
            "uso_nocturno_legitimo",
            "limpieza",
            "guardia",
            "ocupacion_extendida",
            "feriados",
        ],
    }
    write_json(report_path, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepara lecturas limpias ML")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="/app/data/processed/ml/readings_clean.parquet")
    parser.add_argument("--report-output", default="/app/data/processed/ml/cleaning_report.json")
    args = parser.parse_args()
    report = prepare_dataset(args.input, args.output, args.report_output)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()




