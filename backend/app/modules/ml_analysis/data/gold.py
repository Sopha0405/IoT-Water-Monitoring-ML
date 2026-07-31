from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.modules.ml_analysis.data.io import read_dataframe, write_dataframe, write_json
from app.modules.ml_analysis.features.constants import FEATURE_NAMES, FEATURE_SCHEMA_VERSION
from app.modules.ml_analysis.features.extractor import extract_features
from app.modules.ml_analysis.streaming.types import FlowReading
from app.modules.ml_analysis.data.common import LOCAL_TIMEZONE, SAMPLE_SECONDS, add_interval_columns, stable_frame_hash

WINDOW_AUDIT_COLUMNS = [
    "window_start",
    "window_end",
    "sensor_id",
    "actual_label",
    "label_status",
    "actual_type",
    "anomaly_severity",
    "event_id",
    "anomaly_active_ratio",
    "post_event_ratio",
    "is_sensor_error",
    "is_normal_difficult",
    "baseline_train_eligible",
]


def build_gold(input_path: str | Path, output_path: str | Path, report_path: str | Path) -> dict[str, Any]:
    frame = add_interval_columns(read_dataframe(input_path))
    rows: list[dict[str, Any]] = []
    discarded = {"incomplete": 0, "irregular": 0, "cross_day": 0, "non_finite": 0}
    for sensor_id, sensor_frame in frame.sort_values(["sensor_id", "timestamp"]).groupby("sensor_id", sort=True):
        sensor_frame = sensor_frame.reset_index(drop=True)
        local_ts = sensor_frame["timestamp"].dt.tz_convert(LOCAL_TIMEZONE)
        sensor_frame["_window_block"] = local_ts.dt.floor("5min")
        for _, window_index in sensor_frame.groupby("_window_block", sort=True).groups.items():
            positions = np.asarray(window_index, dtype=int)
            window = sensor_frame.iloc[positions].copy()
            if len(window) != 60:
                discarded["incomplete"] += 1
                continue
            if window["is_irregular_interval"].iloc[1:].any():
                discarded["irregular"] += 1
                continue
            local_dates = window["timestamp"].dt.tz_convert(LOCAL_TIMEZONE).dt.date
            if local_dates.nunique() != 1:
                discarded["cross_day"] += 1
                continue
            if not np.isfinite(window["flow_lpm"].to_numpy(dtype=float)).all():
                discarded["non_finite"] += 1
                continue
            end_position = int(positions[-1])
            history = sensor_frame.iloc[max(0, end_position - 359) : end_position + 1]
            readings = _readings_from_frame(window, sensor_id)
            history_readings = _readings_from_frame(history, sensor_id)
            micro_windows = _micro_windows_before(history)
            features = extract_features(readings, history_readings, {}, {"microflow_windows": micro_windows, "timezone": LOCAL_TIMEZONE})
            event_ids = sorted(str(value) for value in window["event_id"].dropna().unique() if str(value))
            label_ratio = float(window["actual_label"].eq(1).mean())
            post_ratio = float(window["label_status"].astype("string").str.contains("post", case=False, na=False).mean())
            row = {
                **features,
                "window_start": window["timestamp"].iloc[0],
                "window_end": window["timestamp"].iloc[-1],
                "sensor_id": str(sensor_id),
                "actual_label": _window_label(window, label_ratio),
                "label_status": _mode_or_default(window["label_status"], "unknown"),
                "actual_type": _mode_or_default(window["actual_type"], "normal"),
                "anomaly_severity": _mode_or_default(window["anomaly_severity"], "none"),
                "event_id": event_ids[0] if len(event_ids) == 1 else ("MULTIPLE_EVENTS" if event_ids else None),
                "anomaly_active_ratio": label_ratio,
                "post_event_ratio": post_ratio,
                "is_sensor_error": bool(window.get("is_sensor_error", pd.Series(False, index=window.index)).any()),
                "is_normal_difficult": bool(window.get("is_normal_difficult", pd.Series(False, index=window.index)).any()),
                "baseline_train_eligible": bool(window.get("baseline_train_eligible", pd.Series(False, index=window.index)).all()),
            }
            rows.append(row)
    gold = pd.DataFrame(rows)
    if not gold.empty:
        gold = gold[FEATURE_NAMES + WINDOW_AUDIT_COLUMNS]
    write_dataframe(gold, output_path)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_names": FEATURE_NAMES,
        "feature_count": len(FEATURE_NAMES),
        "input_path": str(input_path),
        "output_path": str(output_path),
        "windows": int(len(gold)),
        "discarded_windows": discarded,
        "dataset_hash": stable_frame_hash(gold) if len(gold) else None,
        "audit_columns": WINDOW_AUDIT_COLUMNS,
    }
    write_json(report_path, report)
    return report


def _to_reading(row: dict[str, Any], sensor_id: str) -> FlowReading:
    return FlowReading(
        timestamp=row["timestamp"].to_pydatetime() if hasattr(row["timestamp"], "to_pydatetime") else row["timestamp"],
        sensor_id=str(sensor_id),
        flow_lpm=float(row["flow_lpm"]),
        sequence_number=None,
        sample_seconds=SAMPLE_SECONDS,
        status="ok",
        simulated=False,
        scenario=None,
        scenario_event_id=None,
    )


def _readings_from_frame(frame: pd.DataFrame, sensor_id: str) -> list[FlowReading]:
    timestamps = frame["timestamp"].tolist()
    flows = frame["flow_lpm"].to_numpy(dtype=float)
    return [
        FlowReading(
            timestamp=timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else timestamp,
            sensor_id=str(sensor_id),
            flow_lpm=float(flow),
            sequence_number=None,
            sample_seconds=SAMPLE_SECONDS,
            status="ok",
            simulated=False,
            scenario=None,
            scenario_event_id=None,
        )
        for timestamp, flow in zip(timestamps, flows)
    ]


def _window_label(window: pd.DataFrame, label_ratio: float) -> int:
    types = window["actual_type"].astype("string").str.lower()
    if types.str.contains("peak|pico", na=False).any():
        return 1
    if types.str.contains("micro", na=False).any():
        return int(label_ratio >= 0.80)
    if types.str.contains("sustained|fuga|leak|growing", na=False).any():
        return int(label_ratio >= 0.20)
    return int(label_ratio >= 0.50)


def _mode_or_default(series: pd.Series, default: str) -> str:
    clean = series.dropna().astype(str)
    clean = clean.loc[clean.ne("")]
    if clean.empty:
        return default
    return str(clean.mode().iloc[0])


def _micro_windows_before(frame: pd.DataFrame) -> int:
    if len(frame) < 60:
        return 0
    count = 0
    for start in range(max(0, len(frame) - 360), len(frame), 60):
        window = frame.iloc[start : start + 60]
        if len(window) == 60 and ((window["flow_lpm"] >= 0.03) & (window["flow_lpm"] <= 0.50)).mean() >= 0.90:
            count += 1
        else:
            count = 0
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Construye ventanas Gold ML")
    parser.add_argument("--input", default="/app/data/processed/ml/readings_clean.parquet")
    parser.add_argument("--output", default="/app/data/processed/ml/windows_gold.parquet")
    parser.add_argument("--report-output", default="/app/data/processed/ml/gold_report.json")
    args = parser.parse_args()
    report = build_gold(args.input, args.output, args.report_output)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()




