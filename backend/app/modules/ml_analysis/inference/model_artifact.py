from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from app.modules.ml_analysis.features.constants import FEATURE_NAMES, FEATURE_SCHEMA_VERSION
from app.modules.ml_analysis.features.extractor import extract_features
from app.modules.ml_analysis.streaming.types import FlowReading


class ModelArtifact:
    """Runtime wrapper for the official 24-feature Isolation Forest artifact."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.model = payload["model"]
        self.scaler = payload["scaler"]
        self.threshold = float(payload["threshold"])
        self.feature_names = list(payload["feature_names"])
        self.feature_schema_version = str(payload["feature_schema_version"])
        self.metrics = payload.get("metrics", {})
        self.feature_context = payload.get("feature_context", {})
        self.training_data = payload.get("training_data")
        self.trained_at = _parse_datetime(payload.get("trained_at"))
        self._validate()

    @classmethod
    def load(cls, path: str | Path) -> "ModelArtifact":
        payload = joblib.load(path)
        if not isinstance(payload, dict):
            raise RuntimeError("Artefacto ML incompatible: se esperaba dict joblib")
        return cls(payload)

    def save(self, path: str | Path) -> None:
        self._validate()
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.payload, target)

    def decision_scores(self, X: np.ndarray) -> np.ndarray:
        matrix = np.asarray(X, dtype=float)
        if matrix.ndim != 2 or matrix.shape[1] != len(FEATURE_NAMES):
            raise ValueError("La matriz debe contener exactamente 24 features")
        return self.model.decision_function(self.scaler.transform(matrix)).astype(float)

    def predict(self, features: np.ndarray | dict[str, float]) -> dict[str, Any]:
        if isinstance(features, dict):
            X = np.asarray([[features[name] for name in FEATURE_NAMES]], dtype=float)
        else:
            X = np.asarray(features, dtype=float)
            if X.ndim == 1:
                X = X.reshape(1, -1)
        score = float(self.decision_scores(X)[0])
        prediction = "anomaly" if score < self.threshold else "normal"
        distance = abs(score - self.threshold)
        return {
            "score": score,
            "prediction": prediction,
            "severity": _severity(score, self.threshold),
            "confidence": float(min(1.0, distance / max(abs(self.threshold), 1e-6))),
        }

    def extract_features(self, readings: np.ndarray, sensor_id: str, context: dict[str, Any] | None = None) -> np.ndarray:
        context = context or {}
        timestamp = context.get("timestamp")
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        values = np.asarray(readings, dtype=float).reshape(-1)
        sample_seconds = int(context.get("sample_seconds", 5))
        start = timestamp - timedelta(seconds=sample_seconds * (len(values) - 1))
        window = [
            FlowReading(
                timestamp=start + timedelta(seconds=sample_seconds * index),
                sensor_id=sensor_id,
                flow_lpm=float(value),
                sequence_number=index + 1,
                sample_seconds=sample_seconds,
                status="ok",
                simulated=False,
                scenario=None,
                scenario_event_id=None,
            )
            for index, value in enumerate(values)
        ]
        features = extract_features(window, window, self.feature_context, context)
        return np.asarray([[features[name] for name in FEATURE_NAMES]], dtype=float)

    def _validate(self) -> None:
        if self.feature_schema_version != FEATURE_SCHEMA_VERSION:
            raise RuntimeError("Artefacto ML incompatible: schema no oficial")
        if self.feature_names != FEATURE_NAMES or len(self.feature_names) != 24:
            raise RuntimeError("Artefacto ML incompatible: se requieren 24 features oficiales")
        if "threshold" not in self.payload:
            raise RuntimeError("Artefacto ML incompatible: falta threshold")


def _severity(score: float, threshold: float) -> str:
    if score >= threshold:
        return "normal"
    gap = threshold - score
    if gap > 0.20:
        return "high"
    if gap > 0.08:
        return "medium"
    return "low"


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)




