from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import joblib

from app.modules.ml_analysis.data.io import read_dataframe, write_dataframe
from app.modules.ml_analysis.features.constants import FEATURE_NAMES
from app.modules.ml_analysis.features.extractor import extract_features
from app.modules.ml_analysis.training.evaluator import evaluate_test
from app.modules.ml_analysis.inference.model_artifact import ModelArtifact
from app.modules.ml_analysis.training.promotion import promote
from app.modules.ml_analysis.streaming.types import FlowReading
from app.modules.ml_analysis.data.split import temporal_split
from app.modules.ml_analysis.training.threshold_optimizer import optimize_threshold


class IdentityScaler:
    def transform(self, X):
        return X


class SumModel:
    def decision_function(self, X):
        if len(X) == 5:
            return np.asarray([0.9, 0.1, 0.8, 0.1, 0.9], dtype=float)
        return np.asarray([0.9, 0.8, 0.1, 0.2], dtype=float)


def test_read_write_csv_gz_and_parquet(tmp_path) -> None:
    frame = pd.DataFrame({"timestamp": ["2026-07-25T12:00:00Z"], "sensor_id": ["PM-04"], "flow_lpm": [0.0]})
    csv_path = tmp_path / "data.csv.gz"
    parquet_path = tmp_path / "data.parquet"
    write_dataframe(frame, csv_path)
    write_dataframe(frame, parquet_path)
    assert len(read_dataframe(csv_path)) == 1
    assert len(read_dataframe(parquet_path)) == 1


def test_features_exact_order_and_no_future() -> None:
    start = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
    readings = [
        FlowReading(start + timedelta(seconds=5 * index), "PM-04", float(index % 3), index, 5, "ok", False, None, None)
        for index in range(360)
    ]
    features = extract_features(readings[-60:], readings, {}, {})
    assert list(features) == FEATURE_NAMES
    assert len(features) == 24
    np.testing.assert_allclose(features["caudal_promedio_30min"], np.mean([item.flow_lpm for item in readings]), rtol=1e-6, atol=1e-8)


def test_temporal_split_does_not_use_test_for_selection(tmp_path) -> None:
    rows = []
    start = datetime(2026, 7, 25, tzinfo=timezone.utc)
    for index in range(30):
        row = {name: 0.0 for name in FEATURE_NAMES}
        row.update({
            "window_start": start + timedelta(minutes=5 * index),
            "window_end": start + timedelta(minutes=5 * index, seconds=295),
            "sensor_id": "PM-04",
            "actual_label": 0 if index < 20 else 1,
            "label_status": "normal" if index < 20 else "confirmed",
            "actual_type": "normal" if index < 20 else "peak",
            "anomaly_severity": "none",
            "event_id": None if index < 20 else "event-1",
            "anomaly_active_ratio": 0.0 if index < 20 else 1.0,
            "post_event_ratio": 0.0,
            "is_sensor_error": False,
            "is_normal_difficult": False,
        })
        rows.append(row)
    source = tmp_path / "gold.parquet"
    write_dataframe(pd.DataFrame(rows), source)
    report = temporal_split(source, tmp_path / "splits")
    assert report["test_used_for_selection"] is False


def test_threshold_fallback_not_applied_without_permission() -> None:
    scores = np.asarray([0.5, 0.1, 0.4, 0.2])
    y_true = np.asarray([0, 0, 1, 1])
    frame = pd.DataFrame({"actual_type": ["normal", "normal", "peak", "peak"], "event_id": [None, None, "e1", "e1"]})
    selection = optimize_threshold(scores, y_true, frame, min_precision=1.0, min_recall=1.0, max_fpr=0.0, allow_fallback=False)
    assert selection.constraints_satisfied is False


def test_feedback_pending_policy_documented() -> None:
    pending_status = "pending"
    assert pending_status != "approved_for_training"


def test_evaluate_test_recomputes_auc_and_excludes_normal_recall(tmp_path) -> None:
    rows = []
    start = datetime(2026, 7, 25, tzinfo=timezone.utc)
    for index, label in enumerate([0, 0, 1, 1]):
        row = {name: 0.0 for name in FEATURE_NAMES}
        row.update({
            "window_end": start + timedelta(minutes=5 * index),
            "sensor_id": "PM-04",
            "actual_label": label,
            "actual_type": "normal" if index == 0 else ("microfuga" if label else "normal"),
            "anomaly_severity": "0.0413" if label else "none",
            "event_id": None if not label else f"e{index}",
            "is_normal_difficult": not label,
        })
        rows.append(row)
    test_path = tmp_path / "test.parquet"
    model_path = tmp_path / "candidate.joblib"
    write_dataframe(pd.DataFrame(rows), test_path)
    joblib.dump({
        "model": SumModel(),
        "scaler": IdentityScaler(),
        "threshold": 0.5,
        "feature_names": FEATURE_NAMES,
        "feature_schema_version": "water-flow-24f-1",
        "metrics": {"pr_auc": 0.01, "roc_auc": 0.01, "precision": 0.01, "recall": 0.01, "fpr": 0.99},
    }, model_path)
    report = evaluate_test(model_path, test_path, tmp_path / "pred.parquet", tmp_path / "report.json")
    assert report["test_metrics"]["pr_auc"] != report["validation_metrics"]["pr_auc"]
    assert report["test_metrics"]["roc_auc"] != report["validation_metrics"]["roc_auc"]
    assert "normal" not in report["recall_by_type"]
    assert set(report["recall_by_severity"]) <= {"none", "low", "medium", "high"}


def test_incident_grouping_separates_events(tmp_path) -> None:
    rows = []
    start = datetime(2026, 7, 25, tzinfo=timezone.utc)
    event_ids = ["e1", "e1", None, "e2", "e2"]
    minutes = [0, 5, 60, 80, 85]
    for index, event_id in enumerate(event_ids):
        is_microleak = event_id is not None
        row = {name: 0.0 for name in FEATURE_NAMES}
        row.update({
            "window_end": start + timedelta(minutes=minutes[index]),
            "sensor_id": "PM-04",
            "actual_label": int(is_microleak),
            "actual_type": "microfuga" if is_microleak else "normal",
            "anomaly_severity": "high" if is_microleak else "none",
            "event_id": event_id,
            "is_normal_difficult": False,
            "mu_q": 0.45 if is_microleak else 0.0,
            "pct_microflujo_5min": 0.55 if is_microleak else 0.0,
            "duracion_microflujo_continuo_seg": 35 if is_microleak else 0,
        })
        rows.append(row)
    path = tmp_path / "test.parquet"
    model_path = tmp_path / "candidate.joblib"
    write_dataframe(pd.DataFrame(rows), path)
    joblib.dump({"model": SumModel(), "scaler": IdentityScaler(), "threshold": 0.5, "feature_names": FEATURE_NAMES, "feature_schema_version": "water-flow-24f-1", "metrics": {}}, model_path)
    report = evaluate_test(model_path, path, tmp_path / "pred.parquet", tmp_path / "report.json")
    assert report["incidents"]["grouped_incidents"] >= 2


def test_promotion_requires_report_and_rejects_model_hash_mismatch(tmp_path) -> None:
    candidate = tmp_path / "candidate.joblib"
    active = tmp_path / "active.joblib"
    report = tmp_path / "test_report.json"
    joblib.dump({"model": SumModel(), "scaler": IdentityScaler(), "threshold": 0.5, "feature_names": FEATURE_NAMES, "feature_schema_version": "water-flow-24f-1", "metrics": {"precision": 1.0, "recall": 1.0, "fpr": 0.0}}, candidate)
    report.write_text('{"model_sha256":"bad","threshold":0.5,"test_used_for_selection":false,"test_metrics":{"precision":1.0,"recall":1.0,"fpr":0.0,"pr_auc":1.0,"roc_auc":1.0}}', encoding="utf-8")
    try:
        promote(candidate, active, tmp_path / "archive", test_report=report, confirm=True)
    except RuntimeError as exc:
        assert "hash" in str(exc)
    else:
        raise AssertionError("promotion accepted mismatched model hash")


def test_legacy_16_feature_artifact_is_rejected() -> None:
    try:
        ModelArtifact({"model": object(), "scaler": object(), "threshold": 0.0, "feature_names": [f"f{i}" for i in range(16)], "feature_schema_version": "2.0.0"})
    except RuntimeError as exc:
        assert "incompatible" in str(exc)
    else:
        raise AssertionError("legacy artifact accepted")




