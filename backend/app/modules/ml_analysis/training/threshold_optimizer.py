from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score


@dataclass(frozen=True)
class ThresholdSelection:
    threshold: float
    metrics: dict[str, Any]
    constraints_satisfied: bool
    reason: str
    table: pd.DataFrame


def optimize_threshold(
    scores: np.ndarray,
    y_true: np.ndarray,
    validation: pd.DataFrame,
    *,
    min_precision: float = 0.80,
    min_recall: float = 0.60,
    max_fpr: float = 0.02,
    allow_fallback: bool = False,
) -> ThresholdSelection:
    table = build_threshold_table(scores, y_true, validation)
    approved = table.loc[
        (table["precision"] >= min_precision)
        & (table["recall"] >= min_recall)
        & (table["fpr"] <= max_fpr)
    ].copy()
    if not approved.empty:
        selected = approved.sort_values(
            ["f0_5", "precision", "recall", "fpr", "predicted_alert_rate"],
            ascending=[False, False, False, True, True],
        ).iloc[0]
        return ThresholdSelection(float(selected["threshold"]), _row(selected), True, "constraints_satisfied", table)
    best = table.sort_values(
        ["f0_5", "precision", "recall", "fpr", "predicted_alert_rate"],
        ascending=[False, False, False, True, True],
    ).iloc[0]
    if not allow_fallback:
        return ThresholdSelection(float(best["threshold"]), _row(best), False, "constraints_not_satisfied", table)
    return ThresholdSelection(float(best["threshold"]), _row(best), False, "fallback_allowed", table)


def build_threshold_table(scores: np.ndarray, y_true: np.ndarray, validation: pd.DataFrame) -> pd.DataFrame:
    score_values = np.asarray(scores, dtype=float)
    labels = np.asarray(y_true, dtype=int)
    if len(score_values) != len(labels) or len(labels) == 0:
        raise ValueError("scores y y_true deben tener igual longitud no vacia")
    unique = np.unique(score_values)
    percentiles = np.percentile(score_values, [0, 1, 2, 5, 10, 25, 50, 75, 90, 95, 98, 99, 100])
    grid = np.linspace(float(unique.min()), float(unique.max()), min(200, max(20, len(unique))))
    if len(unique) > 250:
        unique = np.quantile(unique, np.linspace(0.0, 1.0, 250))
    thresholds = np.unique(np.concatenate([unique, percentiles, grid, np.asarray([0.0])]))
    pr_auc = _safe_auc(average_precision_score, labels, -score_values)
    roc_auc = _safe_auc(roc_auc_score, labels, -score_values)
    rows = []
    for threshold in thresholds:
        predicted = score_values < threshold
        rows.append({
            **classification_metrics(labels, predicted.astype(int)),
            "threshold": float(threshold),
            "pr_auc": pr_auc,
            "roc_auc": roc_auc,
            "predicted_alert_rate": float(predicted.mean()),
            "recall_by_type": recall_by_group(validation, labels, predicted, "actual_type"),
            "recall_by_event": recall_by_group(validation, labels, predicted, "event_id"),
            "detection_latency_windows": detection_latency(_with_labels(validation, labels), predicted),
        })
    return pd.DataFrame(rows)


def classification_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    labels = np.asarray(y_true, dtype=int)
    predicted = np.asarray(y_pred, dtype=int)
    tp = int(((labels == 1) & (predicted == 1)).sum())
    fp = int(((labels == 0) & (predicted == 1)).sum())
    tn = int(((labels == 0) & (predicted == 0)).sum())
    fn = int(((labels == 1) & (predicted == 0)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    beta_sq = 0.25
    f0_5 = (1 + beta_sq) * precision * recall / (beta_sq * precision + recall) if beta_sq * precision + recall else 0.0
    return {
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "f0_5": float(f0_5),
        "fpr": float(fpr),
        "specificity": float(specificity),
        "balanced_accuracy": float((recall + specificity) / 2.0),
        "false_positives": fp,
        "false_negatives": fn,
        "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
    }


def recall_by_group(frame: pd.DataFrame, y_true: np.ndarray, predicted: np.ndarray, column: str) -> dict[str, float]:
    if column not in frame:
        return {}
    tmp = frame[[column]].copy()
    tmp["y_true"] = y_true
    tmp["predicted"] = predicted.astype(int)
    out: dict[str, float] = {}
    for key, section in tmp.loc[tmp["y_true"].eq(1)].groupby(column, dropna=True):
        total = int(len(section))
        out[str(key)] = float(section["predicted"].sum() / total) if total else 0.0
    return out


def detection_latency(frame: pd.DataFrame, predicted: np.ndarray) -> dict[str, float]:
    if "event_id" not in frame or "actual_label" not in frame:
        return {}
    tmp = frame.copy()
    tmp["predicted"] = predicted.astype(int)
    latencies = []
    for _, section in tmp.loc[tmp["actual_label"].eq(1) & tmp["event_id"].notna()].groupby("event_id"):
        detected = section.reset_index(drop=True).index[section["predicted"].to_numpy(dtype=bool)]
        if len(detected):
            latencies.append(int(detected[0]))
    if not latencies:
        return {"mean": 0.0, "max": 0.0}
    return {"mean": float(np.mean(latencies)), "max": float(np.max(latencies))}


def _with_labels(frame: pd.DataFrame, labels: np.ndarray) -> pd.DataFrame:
    if "actual_label" in frame:
        return frame
    tmp = frame.copy()
    tmp["actual_label"] = labels
    return tmp


def _safe_auc(func, y_true: np.ndarray, scores: np.ndarray) -> float | None:
    try:
        if len(np.unique(y_true)) < 2:
            return None
        return float(func(y_true, scores))
    except ValueError:
        return None


def _row(row: pd.Series) -> dict[str, Any]:
    data = row.to_dict()
    return {key: (value.item() if hasattr(value, "item") else value) for key, value in data.items() if key != "threshold"}




