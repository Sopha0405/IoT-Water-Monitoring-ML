from __future__ import annotations

import argparse
import itertools
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from app.modules.ml_analysis.data.io import read_dataframe, sha256_file, write_json
from app.modules.ml_analysis.features.constants import FEATURE_NAMES, FEATURE_SCHEMA_VERSION
from app.modules.ml_analysis.training.threshold_optimizer import optimize_threshold
from app.modules.ml_analysis.data.common import stable_frame_hash


def train_grid(
    train_path: str | Path,
    validation_path: str | Path,
    output_path: str | Path,
    report_path: str | Path,
    *,
    max_candidates: int | None = None,
    allow_fallback: bool = False,
) -> dict[str, Any]:
    train = read_dataframe(train_path)
    validation = read_dataframe(validation_path)
    train_clean = train.loc[
        train["actual_label"].eq(0)
        & ~train["is_sensor_error"].fillna(False)
        & train["event_id"].isna()
    ].copy()
    if train_clean.empty:
        raise ValueError("Train no contiene normalidad limpia")
    if validation.empty:
        raise ValueError("Validation esta vacio")
    X_train = train_clean[FEATURE_NAMES].to_numpy(dtype=float)
    X_val = validation[FEATURE_NAMES].to_numpy(dtype=float)
    y_val = validation["actual_label"].to_numpy(dtype=int)
    if len(np.unique(y_val)) < 2:
        if not allow_fallback:
            raise ValueError("Validation debe contener normales y anomalias etiquetadas")
        return _train_unsupervised_candidate(
            train_clean=train_clean,
            validation=validation,
            x_train=X_train,
            x_val=X_val,
            output_path=output_path,
            report_path=report_path,
            train_path=train_path,
            validation_path=validation_path,
        )

    grid = list(itertools.product([100, 200, 300, 500], [0.01, 0.02, 0.03, 0.04, 0.05], ["auto", 0.70, 0.90], [0.70, 0.85, 1.00]))
    if max_candidates is not None:
        grid = grid[:max_candidates]
    candidates: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    best_objects: tuple[StandardScaler, IsolationForest] | None = None
    for n_estimators, contamination, max_samples, max_features in grid:
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        model = IsolationForest(
            n_estimators=n_estimators,
            contamination=contamination,
            max_samples=max_samples,
            max_features=max_features,
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X_train_scaled)
        scores = model.decision_function(scaler.transform(X_val)).astype(float)
        selection = optimize_threshold(scores, y_val, validation, allow_fallback=allow_fallback)
        entry = {
            "params": {
                "n_estimators": n_estimators,
                "contamination": contamination,
                "max_samples": max_samples,
                "max_features": max_features,
                "random_state": 42,
            },
            "threshold": selection.threshold,
            "constraints_satisfied": selection.constraints_satisfied,
            "selection_reason": selection.reason,
            "metrics": selection.metrics,
        }
        candidates.append(entry)
        if selection.constraints_satisfied and _is_better(entry, best):
            best = entry
            best_objects = (scaler, model)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_names": FEATURE_NAMES,
        "train_path": str(train_path),
        "validation_path": str(validation_path),
        "train_sha256": sha256_file(train_path),
        "validation_sha256": sha256_file(validation_path),
        "train_hash": stable_frame_hash(train_clean),
        "validation_hash": stable_frame_hash(validation),
        "constraints": {"precision": 0.80, "recall": 0.60, "fpr": 0.02},
        "candidate_count": len(candidates),
        "candidates": candidates,
        "approved_candidate": best,
        "output_path": str(output_path),
        "active_modified": False,
    }
    if best is None or best_objects is None:
        report["model_saved"] = False
        report["failure_reason"] = "no_candidate_satisfied_constraints"
        write_json(report_path, report)
        if not allow_fallback:
            raise RuntimeError("Ningun candidato cumple Precision>=0.80, Recall>=0.60 y FPR<=0.02")
        return report

    artifact = {
        "artifact_version": "1.0.0",
        "model_type": "IsolationForest",
        "model": best_objects[1],
        "scaler": best_objects[0],
        "threshold": float(best["threshold"]),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_names": FEATURE_NAMES,
        "hyperparameters": best["params"],
        "random_state": 42,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "dataset_hashes": {
            "train": report["train_hash"],
            "validation": report["validation_hash"],
            "train_file_sha256": report["train_sha256"],
            "validation_file_sha256": report["validation_sha256"],
        },
        "metrics": best["metrics"],
        "sensors_compatible": sorted(train_clean["sensor_id"].astype(str).unique().tolist()),
        "exclusions": ["sensor_error", "unknown", "maintenance", "anomalies", "irregular_interval"],
        "code_version": "ml",
        "runtime": {"python": platform.python_version(), "sklearn": sklearn.__version__, "numpy": np.__version__},
    }
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, target)
    report["model_saved"] = True
    report["candidate_sha256"] = sha256_file(target)
    write_json(report_path, report)
    return report


def _is_better(candidate: dict[str, Any], current: dict[str, Any] | None) -> bool:
    if current is None:
        return True
    c = candidate["metrics"]
    b = current["metrics"]
    return (
        c.get("f0_5", 0.0),
        c.get("pr_auc") or 0.0,
        _mean_recall(c.get("recall_by_event", {})),
        -_complexity(candidate["params"]),
    ) > (
        b.get("f0_5", 0.0),
        b.get("pr_auc") or 0.0,
        _mean_recall(b.get("recall_by_event", {})),
        -_complexity(current["params"]),
    )


def _mean_recall(values: dict[str, float]) -> float:
    return float(np.mean(list(values.values()))) if values else 0.0


def _complexity(params: dict[str, Any]) -> float:
    return float(params["n_estimators"])


def _train_unsupervised_candidate(
    *,
    train_clean: pd.DataFrame,
    validation: pd.DataFrame,
    x_train: np.ndarray,
    x_val: np.ndarray,
    output_path: str | Path,
    report_path: str | Path,
    train_path: str | Path,
    validation_path: str | Path,
) -> dict[str, Any]:
    scaler = StandardScaler()
    x_train_scaled = scaler.fit_transform(x_train)
    params = {
        "n_estimators": 300,
        "contamination": 0.02,
        "max_samples": "auto",
        "max_features": 1.0,
        "random_state": 42,
    }
    model = IsolationForest(n_jobs=-1, **params)
    model.fit(x_train_scaled)
    scores = model.decision_function(scaler.transform(x_val)).astype(float)
    threshold = float(np.percentile(scores, 2)) if len(scores) else 0.0
    predicted = scores < threshold if len(scores) else np.asarray([], dtype=bool)
    normal_count = int(len(predicted))
    predicted_alerts = int(predicted.sum()) if normal_count else 0
    normal_acceptance_rate = float(1.0 - predicted.mean()) if normal_count else None
    predicted_alert_rate = float(predicted.mean()) if normal_count else None
    metrics = {
        "precision": None,
        "recall": None,
        "f1": None,
        "specificity": normal_acceptance_rate,
        "fpr": predicted_alert_rate,
        "normal_acceptance_rate": normal_acceptance_rate,
        "predicted_alert_rate": predicted_alert_rate,
        "accepted_windows": int(normal_count - predicted_alerts),
        "predicted_anomaly_windows": predicted_alerts,
        "supervised_metrics_available": False,
        "unavailable_reason": "No existe un conjunto etiquetado suficiente.",
    }
    best = {
        "params": params,
        "threshold": threshold,
        "constraints_satisfied": False,
        "selection_reason": "unsupervised_fallback_no_labeled_validation",
        "metrics": metrics,
    }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_names": FEATURE_NAMES,
        "train_path": str(train_path),
        "validation_path": str(validation_path),
        "train_sha256": sha256_file(train_path),
        "validation_sha256": sha256_file(validation_path),
        "train_hash": stable_frame_hash(train_clean),
        "validation_hash": stable_frame_hash(validation),
        "constraints": {"precision": 0.80, "recall": 0.60, "fpr": 0.02},
        "candidate_count": 1,
        "candidates": [best],
        "approved_candidate": best,
        "output_path": str(output_path),
        "active_modified": False,
        "supervised_metrics_available": False,
    }
    artifact = {
        "artifact_version": "1.0.0",
        "model_type": "IsolationForest",
        "model": model,
        "scaler": scaler,
        "threshold": threshold,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_names": FEATURE_NAMES,
        "hyperparameters": params,
        "random_state": 42,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "dataset_hashes": {
            "train": report["train_hash"],
            "validation": report["validation_hash"],
            "train_file_sha256": report["train_sha256"],
            "validation_file_sha256": report["validation_sha256"],
        },
        "metrics": metrics,
        "sensors_compatible": sorted(train_clean["sensor_id"].astype(str).unique().tolist()),
        "exclusions": ["sensor_error", "unknown", "maintenance", "anomalies", "irregular_interval"],
        "code_version": "ml",
        "runtime": {"python": platform.python_version(), "sklearn": sklearn.__version__, "numpy": np.__version__},
    }
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, target)
    report["model_saved"] = True
    report["candidate_sha256"] = sha256_file(target)
    write_json(report_path, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Entrena grid Isolation Forest ML")
    parser.add_argument("--train", required=True)
    parser.add_argument("--validation", required=True)
    parser.add_argument("--output", default="/app/app/models/ml_analysis/candidate.joblib")
    parser.add_argument("--report-output", default="/app/data/evaluation/ml/training_report.json")
    parser.add_argument("--max-candidates", type=int, default=None)
    parser.add_argument("--allow-fallback", action="store_true")
    args = parser.parse_args()
    try:
        report = train_grid(args.train, args.validation, args.output, args.report_output, max_candidates=args.max_candidates, allow_fallback=args.allow_fallback)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()




