from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from scipy.stats import linregress
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)

FEATURE_NAMES = [
    "mu_q",
    "sigma_q",
    "min_q",
    "max_q",
    "iqr_q",
    "slope_q",
    "v_ventana",
    "delta_v_dia",
    "r_hora",
    "hora_sin",
    "hora_cos",
    "dia_semana",
    "horario_laboral",
    "sensor_id_enc",
]


class IsolationForestModel:
    """Modelo Isolation Forest con escalado fijo para deteccion de anomalias."""

    def __init__(self, model_name: str = "IsolationForest") -> None:
        """Inicializa el modelo, el scaler y el historico usado para reentrenamiento."""
        self.model_name = model_name
        self.scaler: StandardScaler | None = None
        self.model: IsolationForest | None = None
        self.training_data: np.ndarray | None = None
        self.trained_at: datetime | None = None

    def train(self, X_train: np.ndarray, contamination: float = 0.05) -> None:
        """Entrena el scaler y el Isolation Forest solo con datos de entrenamiento."""
        X = self._validate_matrix(X_train)
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)
        self.model = IsolationForest(
            n_estimators=200,
            max_samples="auto",
            contamination=contamination,
            random_state=42,
            n_jobs=-1,
        )
        self.model.fit(X_scaled)
        self.training_data = X.copy()
        self.trained_at = datetime.utcnow()
        logger.info("Modelo IsolationForest entrenado con %s muestras", len(X))

    def predict(self, X: np.ndarray) -> dict[str, Any]:
        """Predice una muestra o matriz y retorna score, severidad, confianza y tipo."""
        if self.model is None or self.scaler is None:
            raise RuntimeError("Modelo no cargado")

        X_valid = self._validate_matrix(X)
        X_scaled = self.scaler.transform(X_valid)
        scores = self.model.decision_function(X_scaled)
        predictions = self.model.predict(X_scaled)
        score = float(scores[0])
        severity = self._classify_severity(score)
        return {
            "score": score,
            "severity": severity,
            "confidence": round(min(99.0, max(1.0, abs(score) * 400.0)), 2),
            "anomaly_type": "normal" if int(predictions[0]) == 1 else "anomalia_no_clasificada",
            "prediction": "normal" if int(predictions[0]) == 1 else "anomaly",
        }

    def save(self, path: str | Path) -> None:
        """Serializa el modelo, scaler y metadatos con joblib."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "model_name": self.model_name,
                "scaler": self.scaler,
                "model": self.model,
                "training_data": self.training_data,
                "trained_at": self.trained_at,
            },
            target,
        )
        logger.info("Modelo guardado en %s", target)

    @classmethod
    def load(cls, path: str | Path) -> "IsolationForestModel":
        """Carga un modelo serializado desde disco."""
        payload = joblib.load(path)
        instance = cls(model_name=payload.get("model_name", "IsolationForest"))
        instance.scaler = payload["scaler"]
        instance.model = payload["model"]
        instance.training_data = payload.get("training_data")
        instance.trained_at = payload.get("trained_at")
        return instance

    def retrain(self, X_new: np.ndarray, labels: list[int] | np.ndarray | None = None) -> None:
        """Reentrena combinando datos historicos con datos nuevos ordenados temporalmente."""
        X_valid = self._validate_matrix(X_new)
        combined = X_valid if self.training_data is None else np.vstack([self.training_data, X_valid])
        self.train(combined)

    def _classify_severity(self, score: float) -> str:
        """Clasifica severidad segun umbrales del score de Isolation Forest."""
        if score >= 0:
            return "normal"
        if score >= -0.05:
            return "anomalo_leve"
        if score >= -0.15:
            return "anomalo_moderado"
        return "anomalo_critico"

    def _extract_features(self, readings: list[float], sensor_id: str, context: dict[str, Any]) -> np.ndarray:
        """Extrae las 14 variables operativas definidas para una ventana temporal."""
        values = np.asarray(readings, dtype=float)
        if values.size == 0:
            raise ValueError("readings no puede estar vacio")
        now = context.get("timestamp") or datetime.utcnow()
        if isinstance(now, str):
            now = datetime.fromisoformat(now)
        slope = float(linregress(np.arange(values.size), values).slope) if values.size > 1 else 0.0
        hour = int(now.hour)
        weekday = int(now.weekday())
        sensor_hash = sum(ord(char) for char in sensor_id) % 10_000
        return np.asarray(
            [[
                float(np.mean(values)),
                float(np.std(values)),
                float(np.min(values)),
                float(np.max(values)),
                float(np.percentile(values, 75) - np.percentile(values, 25)),
                slope,
                float(np.sum(values) * float(context.get("sample_seconds", 5)) / 60.0),
                float(context.get("delta_v_dia", 0.0)),
                float(context.get("r_hora", hour)),
                float(np.sin(2 * np.pi * hour / 24)),
                float(np.cos(2 * np.pi * hour / 24)),
                float(weekday),
                1.0 if weekday < 5 and 7 <= hour < 19 else 0.0,
                float(sensor_hash),
            ]],
            dtype=float,
        )

    def _validate_matrix(self, X: np.ndarray) -> np.ndarray:
        """Valida que la matriz tenga las variables esperadas."""
        matrix = np.asarray(X, dtype=float)
        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)
        if matrix.shape[1] != len(FEATURE_NAMES):
            raise ValueError(f"Se esperaban {len(FEATURE_NAMES)} features y llegaron {matrix.shape[1]}")
        return matrix


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    rng = np.random.default_rng(42)
    synthetic = rng.normal(loc=0.0, scale=1.0, size=(500, len(FEATURE_NAMES)))
    model = IsolationForestModel()
    model.train(synthetic)
    print(model.predict(synthetic[:1]))
