from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class InferenceRequest(BaseModel):
    """Solicitud para analizar un sensor."""

    sensor_id: str = Field(min_length=1, max_length=80)
    shadow_mode: bool = False


class InferenceResponse(BaseModel):
    """Resultado de inferencia del modelo ML."""

    sensor_id: str
    score: float
    severity: str
    confidence: float = Field(ge=0, le=100)
    anomaly_type: str
    prediction: str
    processed_at: datetime
    latency_ms: float


class AlertCreate(BaseModel):
    """Datos necesarios para crear una alerta."""

    device_id: str
    floor: str | None = None
    anomaly_type: str
    severity: str
    risk_percentage: float
    status: str = "pendiente"
    description: str | None = None
    detected_at: datetime


class MLAnalysisCreate(BaseModel):
    """Datos necesarios para persistir un analisis ML."""

    alert_id: int | None = None
    model_name: str = "IsolationForest"
    anomaly_score: float
    prediction: str
    confidence: float = Field(ge=0, le=100)
    processed_at: datetime | None = None


class DriftReport(BaseModel):
    """Reporte de drift estadistico y operativo."""

    generated_at: datetime
    ks_scores: list[float]
    trigger_a: bool
    trigger_b: bool
    trigger_c: bool
    drift_detected: bool


class ModelStatus(BaseModel):
    """Estado de la version activa del modelo."""

    active_version: str | None
    metrics: dict[str, float]
    trained_at: datetime | None
    model_path: str | None


class RetrainRequest(BaseModel):
    """Solicitud de reentrenamiento temporal."""

    sensor_id: str | None = None
    contamination: float = Field(default=0.05, gt=0, lt=0.5)
    shadow_mode: bool = True


class RetrainResponse(BaseModel):
    """Respuesta del proceso de reentrenamiento."""

    accepted: bool
    message: str
    shadow_mode: bool
