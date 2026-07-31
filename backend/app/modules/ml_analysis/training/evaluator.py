from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from app.modules.ml_analysis.alerts.policy import (
    classify_operational_alert_type,
    group_operational_incidents,
    incident_metrics,
    microleak_rule,
)
from app.modules.ml_analysis.data.io import read_dataframe, sha256_file, write_dataframe, write_json
from app.modules.ml_analysis.features.constants import FEATURE_NAMES
from app.modules.ml_analysis.training.threshold_optimizer import classification_metrics, detection_latency, recall_by_group


def evaluate_test(model_path: str | Path, test_path: str | Path, predictions_path: str | Path, report_path: str | Path) -> dict[str, Any]:
    artifact = joblib.load(model_path)
    if artifact.get("feature_names") != FEATURE_NAMES:
        raise RuntimeError("El modelo no coincide con FEATURE_NAMES")
    test = read_dataframe(test_path)
    X = test[FEATURE_NAMES].to_numpy(dtype=float)
    scores = artifact["model"].decision_function(artifact["scaler"].transform(X)).astype(float)
    threshold = float(artifact["threshold"])
    model_predicted = (scores < threshold).astype(int)
    rule_predicted = microleak_rule(test).to_numpy(int)
    predicted = np.maximum(model_predicted, rule_predicted)
    y_true = test["actual_label"].to_numpy(dtype=int)
    predictions = test.copy()
    predictions["decision_score"] = scores
    predictions["decision_threshold"] = threshold
    predictions["model_predicted_anomaly"] = model_predicted
    predictions["rule_predicted_microleak"] = rule_predicted
    predictions["predicted_anomaly"] = predicted
    predictions["anomaly_score"] = -scores
    predictions["anomaly_severity"] = _normalize_severity(predictions.get("anomaly_severity"))
    write_dataframe(predictions, predictions_path)
    base = classification_metrics(y_true, predicted)
    test_metrics = {
        **base,
        "pr_auc": _safe_auc(average_precision_score, y_true, -scores),
        "roc_auc": _safe_auc(roc_auc_score, y_true, -scores),
    }
    validation_metrics = artifact.get("metrics", {})
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_path": str(model_path),
        "model_sha256": sha256_file(model_path),
        "test_path": str(test_path),
        "test_sha256": sha256_file(test_path),
        "threshold": threshold,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "window_metrics": test_metrics,
        "pr_auc": test_metrics["pr_auc"],
        "roc_auc": test_metrics["roc_auc"],
        "recall_by_type": _recall_by_type(predictions, y_true, predicted),
        "recall_by_severity": recall_by_group(predictions, y_true, predicted, "anomaly_severity"),
        "recall_by_event": recall_by_group(predictions, y_true, predicted, "event_id"),
        "precision_by_event": _precision_by_event(predictions),
        "latency": detection_latency(test, predicted),
        "false_positives_per_day": _false_positives_per_day(predictions),
        "false_alerts_by_sensor": _false_alerts_by_sensor(predictions),
        "metrics_by_hour": _metrics_by_hour(predictions),
        "night_metrics": _section_metrics(predictions, lambda hour: hour < 7 or hour >= 19),
        "lunch_metrics": _section_metrics(predictions, lambda hour: 12 <= hour < 14),
        "weekend_metrics": _weekend_metrics(predictions),
        "normal_difficult": _normal_difficult_metrics(predictions),
        "temporal_confirmation": _temporal_confirmation(predictions),
        "incidents": incident_metrics(predictions, merge_by_event_id=True),
        "test_used_for_selection": False,
    }
    write_json(report_path, report)
    return report


def _precision_by_event(frame: pd.DataFrame) -> dict[str, float]:
    out: dict[str, float] = {}
    for event_id, section in frame.loc[frame["event_id"].notna()].groupby("event_id"):
        predicted = int(section["predicted_anomaly"].sum())
        true = int(((section["predicted_anomaly"] == 1) & (section["actual_label"] == 1)).sum())
        out[str(event_id)] = float(true / predicted) if predicted else 0.0
    return out


def _false_positives_per_day(frame: pd.DataFrame) -> dict[str, int]:
    tmp = frame.loc[frame["actual_label"].eq(0) & frame["predicted_anomaly"].eq(1)].copy()
    if tmp.empty:
        return {}
    tmp["day"] = pd.to_datetime(tmp["window_end"], utc=True).dt.date.astype(str)
    return {str(key): int(value) for key, value in tmp.groupby("day").size().items()}


def _false_alerts_by_sensor(frame: pd.DataFrame) -> dict[str, int]:
    tmp = frame.loc[frame["actual_label"].eq(0) & frame["predicted_anomaly"].eq(1)]
    return {str(key): int(value) for key, value in tmp.groupby("sensor_id").size().items()}


def _metrics_by_hour(frame: pd.DataFrame) -> dict[str, Any]:
    tmp = frame.copy()
    tmp["hour"] = pd.to_datetime(tmp["window_end"], utc=True).dt.tz_convert("America/La_Paz").dt.hour
    return {str(hour): classification_metrics(section["actual_label"].to_numpy(int), section["predicted_anomaly"].to_numpy(int)) for hour, section in tmp.groupby("hour")}


def _section_metrics(frame: pd.DataFrame, predicate) -> dict[str, Any]:
    hours = pd.to_datetime(frame["window_end"], utc=True).dt.tz_convert("America/La_Paz").dt.hour
    section = frame.loc[hours.map(predicate)]
    if section.empty:
        return {}
    return classification_metrics(section["actual_label"].to_numpy(int), section["predicted_anomaly"].to_numpy(int))


def _weekend_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    weekdays = pd.to_datetime(frame["window_end"], utc=True).dt.tz_convert("America/La_Paz").dt.weekday
    section = frame.loc[weekdays >= 5]
    if section.empty:
        return {}
    return classification_metrics(section["actual_label"].to_numpy(int), section["predicted_anomaly"].to_numpy(int))


def _normal_difficult_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    section = frame.loc[frame["is_normal_difficult"].fillna(False)]
    if section.empty:
        return {}
    metrics = classification_metrics(section["actual_label"].to_numpy(int), section["predicted_anomaly"].to_numpy(int))
    confusion = metrics["confusion_matrix"]
    return {
        "count": int(len(section)),
        "true_negatives": confusion["tn"],
        "false_positives": confusion["fp"],
        "specificity": metrics["specificity"],
        "fpr": metrics["fpr"],
        "false_alert_rate": metrics["fpr"],
        "window_metrics": metrics,
    }


def _temporal_confirmation(frame: pd.DataFrame) -> dict[str, Any]:
    incidents = group_operational_incidents(frame, merge_by_event_id=True)
    out = {"raw": int(frame["predicted_anomaly"].sum()), "two_of_three": 0, "two_consecutive": 0, "microflow_six": 0, "grouped_alerts": len(incidents)}
    for _, sensor in frame.sort_values("window_end").groupby("sensor_id"):
        preds = sensor["predicted_anomaly"].to_numpy(int)
        micro = microleak_rule(sensor).to_numpy(bool)
        out["two_of_three"] += sum(preds[max(0, i - 2) : i + 1].sum() >= 2 for i in range(len(preds)))
        out["two_consecutive"] += sum(i > 0 and preds[i] and preds[i - 1] for i in range(len(preds)))
        out["microflow_six"] += sum(i >= 5 and micro[i - 5 : i + 1].all() for i in range(len(micro)))
    return out


def _normalize_severity(values: pd.Series | None) -> pd.Series:
    if values is None:
        return pd.Series(dtype=str)
    valid = {"low", "medium", "high", "none"}
    mapped = values.fillna("none").astype(str).str.lower().str.strip()
    mapped = mapped.replace({"normal": "none", "minor": "low", "moderate": "medium", "critical": "high"})
    return mapped.where(mapped.isin(valid), "none")


def _recall_by_type(frame: pd.DataFrame, y_true: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    allowed = {"microfuga", "fuga_sostenida", "pico_anomalo", "consumo_creciente"}
    tmp = frame.copy()
    tmp["predicted_tmp"] = predicted.astype(int)
    tmp["actual_type"] = tmp.get("actual_type", "").fillna("").astype(str).str.lower().str.strip()
    tmp = tmp.loc[tmp["actual_label"].eq(1) & tmp["actual_type"].isin(allowed)]
    return recall_by_group(tmp, tmp["actual_label"].to_numpy(int), tmp["predicted_tmp"].to_numpy(int), "actual_type") if not tmp.empty else {}


def _alert_type(row: pd.Series) -> str:
    return classify_operational_alert_type(row)


def _safe_auc(func, y_true: np.ndarray, scores: np.ndarray) -> float | None:
    if len(np.unique(y_true)) < 2:
        return None
    return float(func(y_true, scores))


def main() -> None:
    parser = argparse.ArgumentParser(description="Evalua candidate una sola vez sobre test")
    parser.add_argument("--model", required=True)
    parser.add_argument("--test", required=True)
    parser.add_argument("--predictions-output", default="/app/data/evaluation/ml/test_predictions.parquet")
    parser.add_argument("--report-output", default="/app/data/evaluation/ml/test_report.json")
    args = parser.parse_args()
    report = evaluate_test(args.model, args.test, args.predictions_output, args.report_output)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=_json_default))


def _json_default(value):
    if isinstance(value, np.generic):
        return value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


if __name__ == "__main__":
    main()




