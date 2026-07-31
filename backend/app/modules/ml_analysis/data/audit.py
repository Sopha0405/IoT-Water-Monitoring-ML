from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from app.modules.ml_analysis.data.io import read_dataframe, sha256_file, write_json
from app.modules.ml_analysis.data.common import (
    LOCAL_TIMEZONE,
    SAMPLE_SECONDS,
    add_interval_columns,
    normalize_reading_columns,
)


def audit_dataset(input_path: str | Path, report_path: str | Path) -> dict[str, Any]:
    source = Path(input_path)
    raw = read_dataframe(source)
    frame = normalize_reading_columns(raw)
    critical_errors: list[str] = []
    if "timestamp" not in frame.columns:
        critical_errors.append("missing_timestamp")
    if "sensor_id" not in frame.columns:
        critical_errors.append("missing_sensor_id")
    if "flow_lpm" not in frame.columns:
        critical_errors.append("missing_flow_lpm")

    if critical_errors:
        report = _base_report(source, raw, critical_errors)
        write_json(report_path, report)
        return report

    frame = add_interval_columns(frame)
    numeric = frame["flow_lpm"].to_numpy(dtype=float, na_value=np.nan)
    invalid_ts = int(frame["timestamp"].isna().sum())
    duplicate_count = int(frame["is_duplicate"].sum())
    negative_count = int(frame["flow_lpm"].lt(0).sum())
    nan_count = int(frame["flow_lpm"].isna().sum())
    infinite_count = int(np.isinf(numeric).sum())
    irregular_count = int(frame["is_irregular_interval"].sum())
    sensor_errors = int(frame["status"].isin({"sensor_error", "desconectado", "error_lectura", "offline"}).sum())
    if invalid_ts:
        critical_errors.append("invalid_timestamps")
    if negative_count:
        critical_errors.append("negative_flow")
    if infinite_count:
        critical_errors.append("infinite_flow")
    if duplicate_count:
        critical_errors.append("duplicate_sensor_timestamp")

    flow = frame["flow_lpm"].dropna()
    daily = (
        frame.assign(volume_l=frame["flow_lpm"].clip(lower=0) * SAMPLE_SECONDS / 60.0)
        .groupby(["sensor_id", "local_date"], dropna=False)["volume_l"]
        .sum()
        .reset_index()
    )
    interval_summary = frame.loc[frame["interval_seconds"].notna(), "interval_seconds"].describe().to_dict()
    event_counts = frame["actual_type"].fillna("none").astype(str).value_counts(dropna=False).to_dict()
    report = {
        **_base_report(source, raw, critical_errors),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "timezone": LOCAL_TIMEZONE,
        "columns": list(raw.columns),
        "canonical_columns": list(frame.columns),
        "timestamp_min": frame["timestamp"].min().isoformat() if frame["timestamp"].notna().any() else None,
        "timestamp_max": frame["timestamp"].max().isoformat() if frame["timestamp"].notna().any() else None,
        "sensors": sorted(frame["sensor_id"].dropna().astype(str).unique().tolist()),
        "duplicates": duplicate_count,
        "nan_flow": nan_count,
        "infinite_flow": infinite_count,
        "negative_flow": negative_count,
        "invalid_timestamps": invalid_ts,
        "irregular_intervals": irregular_count,
        "missing_packets_estimated": int(frame.loc[frame["interval_seconds"] > SAMPLE_SECONDS, "interval_seconds"].sub(SAMPLE_SECONDS).div(SAMPLE_SECONDS).round().sum()),
        "out_of_order": int(frame["is_out_of_order"].sum()),
        "daily_restarts": int((frame["interval_seconds"] < 0).sum()),
        "sensor_errors": sensor_errors,
        "flow_distribution": _describe_flow(flow),
        "zero_flow_percentage": float((frame["flow_lpm"].fillna(0) <= 0.03).mean()),
        "daily_volume_liters": {
            "rows": int(len(daily)),
            "min": float(daily["volume_l"].min()) if len(daily) else 0.0,
            "max": float(daily["volume_l"].max()) if len(daily) else 0.0,
            "mean": float(daily["volume_l"].mean()) if len(daily) else 0.0,
        },
        "incomplete_days": int((frame.groupby(["sensor_id", "local_date"]).size() < 12 * 60).sum()),
        "overlapping_events": _count_overlapping_events(frame),
        "injected_anomalies": int(frame["actual_type"].astype("string").str.contains("leak|fuga|peak|pico|growing", case=False, na=False).sum()),
        "normal_difficult": int(frame["label_status"].astype("string").str.contains("difficult|guard|clean|night|feriado", case=False, na=False).sum()),
        "post_event_periods": int(frame["label_status"].astype("string").str.contains("post", case=False, na=False).sum()),
        "event_counts_by_type": event_counts,
        "severity_counts": frame["anomaly_severity"].fillna("none").astype(str).value_counts(dropna=False).to_dict(),
        "hour_counts": frame["timestamp"].dt.tz_convert(LOCAL_TIMEZONE).dt.hour.value_counts().sort_index().to_dict(),
        "weekend_rows": int(frame["timestamp"].dt.tz_convert(LOCAL_TIMEZONE).dt.weekday.ge(5).sum()),
        "training_allowed": not critical_errors,
    }
    write_json(report_path, report)
    return report


def _base_report(source: Path, raw, critical_errors: list[str]) -> dict[str, Any]:
    return {
        "input_path": str(source),
        "sha256": sha256_file(source) if source.exists() else None,
        "rows": int(len(raw)),
        "critical_errors": critical_errors,
    }


def _describe_flow(flow) -> dict[str, float]:
    if len(flow) == 0:
        return {}
    return {key: float(value) for key, value in flow.describe(percentiles=[0.25, 0.5, 0.75, 0.9, 0.99]).to_dict().items()}


def _count_overlapping_events(frame) -> int:
    active = frame.loc[frame["event_id"].notna() & frame["event_id"].astype(str).ne("")]
    if active.empty:
        return 0
    return int(active.groupby(["sensor_id", "timestamp"])["event_id"].nunique().gt(1).sum())


def main() -> None:
    parser = argparse.ArgumentParser(description="Audita un dataset historico ML")
    parser.add_argument("--input", required=True)
    parser.add_argument("--report", default="/app/data/processed/ml/audit_report.json")
    args = parser.parse_args()
    report = audit_dataset(args.input, args.report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report.get("critical_errors"):
        sys.exit(2)


if __name__ == "__main__":
    main()




