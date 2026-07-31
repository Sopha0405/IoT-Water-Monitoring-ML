from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from app.modules.ml_analysis.data.io import read_dataframe, write_dataframe, write_json
from app.modules.ml_analysis.features.constants import FEATURE_NAMES
from app.modules.ml_analysis.data.common import stable_frame_hash


def temporal_split(
    input_path: str | Path,
    output_dir: str | Path,
    train_ratio: float = 0.70,
    validation_ratio: float = 0.15,
    test_ratio: float = 0.15,
) -> dict[str, Any]:
    if abs(train_ratio + validation_ratio + test_ratio - 1.0) > 1e-9:
        raise ValueError("Los ratios deben sumar 1.0")
    frame = read_dataframe(input_path).sort_values(["sensor_id", "window_end"]).reset_index(drop=True)
    partitions = {"train": [], "validation": [], "test": []}
    split_details: dict[str, Any] = {}
    for sensor_id, sensor_frame in frame.groupby("sensor_id", sort=True):
        groups = _event_safe_groups(sensor_frame)
        total = sum(len(group) for group in groups)
        train_limit = total * train_ratio
        validation_limit = total * (train_ratio + validation_ratio)
        cursor = 0
        detail = {
            "groups": 0,
            "rows_by_partition": {"train": 0, "validation": 0, "test": 0},
            "event_groups": [],
        }
        for group in groups:
            next_cursor = cursor + len(group)
            target = "train" if next_cursor <= train_limit else "validation" if next_cursor <= validation_limit else "test"
            partitions[target].append(group)
            detail["groups"] += 1
            detail["rows_by_partition"][target] += int(len(group))
            event_id = _event_id(group)
            if event_id is not None:
                detail["event_groups"].append({"partition": target, "rows": int(len(group)), "event_id": event_id})
            cursor = next_cursor
        split_details[str(sensor_id)] = detail

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, pd.DataFrame] = {}
    for name, parts in partitions.items():
        part = pd.concat(parts, ignore_index=True) if parts else frame.iloc[0:0].copy()
        if name == "train":
            eligible = part["baseline_train_eligible"].fillna(False) if "baseline_train_eligible" in part else pd.Series(False, index=part.index)
            part = part.loc[
                part["actual_label"].eq(0)
                & (
                    part["label_status"].astype("string").str.lower().isin(["clean", "normal", "ok", "unknown", "baseline_normal"]).fillna(False)
                    | eligible
                )
                & ~part["is_sensor_error"].fillna(False)
                & part["event_id"].isna()
            ].copy()
        outputs[name] = part
        write_dataframe(part, output / f"{name}.parquet")

    references = _hourly_references(outputs["train"])
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_path": str(input_path),
        "ratios": {"train": train_ratio, "validation": validation_ratio, "test": test_ratio},
        "rows": {name: int(len(part)) for name, part in outputs.items()},
        "hashes": {name: stable_frame_hash(part) if len(part) else None for name, part in outputs.items()},
        "event_safe_split": split_details,
        "test_used_for_selection": False,
        "feature_names": FEATURE_NAMES,
        "hourly_references_from_train_only": references,
    }
    write_json(output / "split_report.json", report)
    return report


def _event_safe_groups(frame: pd.DataFrame) -> list[pd.DataFrame]:
    groups: list[pd.DataFrame] = []
    index = 0
    rows = list(frame.iterrows())
    while index < len(rows):
        row_index, row = rows[index]
        event = row.get("event_id")
        event = str(event) if pd.notna(event) and str(event) else None
        if event is None:
            groups.append(frame.loc[[row_index]])
            index += 1
            continue
        current = [row_index]
        index += 1
        while index < len(rows):
            next_index, next_row = rows[index]
            next_event = next_row.get("event_id")
            next_event = str(next_event) if pd.notna(next_event) and str(next_event) else None
            if next_event != event:
                break
            current.append(next_index)
            index += 1
        groups.append(frame.loc[current])
    return groups


def _event_id(frame: pd.DataFrame) -> str | None:
    values = [str(value) for value in frame["event_id"].dropna().unique() if str(value)]
    return values[0] if len(values) == 1 else None


def _hourly_references(train: pd.DataFrame) -> dict[str, dict[str, float]]:
    if train.empty:
        return {}
    frame = train.copy()
    frame["hour"] = pd.to_datetime(frame["window_end"], utc=True).dt.tz_convert("America/La_Paz").dt.hour
    refs: dict[str, dict[str, float]] = {}
    for sensor_id, sensor_frame in frame.groupby("sensor_id", sort=True):
        refs[str(sensor_id)] = {str(int(hour)): float(value) for hour, value in sensor_frame.groupby("hour")["mu_q"].mean().items()}
    return refs


def main() -> None:
    parser = argparse.ArgumentParser(description="Split temporal ML")
    parser.add_argument("--input", default="/app/data/processed/ml/windows_gold.parquet")
    parser.add_argument("--output-dir", default="/app/data/processed/ml/splits")
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--validation-ratio", type=float, default=0.15)
    parser.add_argument("--test-ratio", type=float, default=0.15)
    args = parser.parse_args()
    report = temporal_split(args.input, args.output_dir, args.train_ratio, args.validation_ratio, args.test_ratio)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()




