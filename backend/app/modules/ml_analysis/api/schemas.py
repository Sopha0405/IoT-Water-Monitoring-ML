from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class InferenceRequest(BaseModel):
    sensor_id: str = Field(min_length=1, max_length=80)


class InferenceResponse(BaseModel):
    sensor_id: str
    model_version: str | None = None
    score: float
    severity: str
    confidence: float = Field(ge=0, le=100)
    anomaly_type: str
    prediction: str
    observed_value: float | None = None
    window_start: datetime
    window_end: datetime
    samples_used: int = Field(ge=60, le=60)
    processed_at: datetime
    latency_ms: float = Field(ge=0)


class AlertCreate(BaseModel):
    device_id: str
    floor: str | None = None
    anomaly_type: str
    severity: str
    risk_percentage: float = Field(ge=0, le=100)
    status: str = "pendiente"
    description: str | None = None
    detected_at: datetime


class MLAnalysisCreate(BaseModel):
    alert_id: int | None = None
    device_id: str | None = None
    floor: str | None = None
    observed_value: float | None = None
    model_name: str = "IsolationForest"
    anomaly_score: float
    prediction: str
    confidence: float = Field(ge=0, le=100)
    processed_at: datetime | None = None


class DriftReport(BaseModel):
    generated_at: datetime
    feature_names: list[str]
    ks_scores: list[float]
    ks_pvalues: list[float]
    trigger_a: bool
    trigger_b: bool
    trigger_c: bool
    drift_detected: bool


class ModelStatus(BaseModel):
    """
    Estado del modelo activo y del candidato.

    Las mÃ©tricas usan Any porque el reporte 80/20 contiene valores numÃ©ricos,
    booleanos, textos, listas y diccionarios anidados.
    """

    active_version: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    trained_at: datetime | None = None
    model_path: str | None = None
    promoted_at: datetime | None = None

    candidate_version: str | None = None
    candidate_metrics: dict[str, Any] = Field(default_factory=dict)
    candidate_trained_at: datetime | None = None
    candidate_model_path: str | None = None
    metric_deltas: dict[str, float] = Field(default_factory=dict)


class RetrainRequest(BaseModel):
    dataset_path: str = "/app/data/processed/pm04_features.csv"
    reference_path: str = "/app/data/processed/ml/reference.json"
    contamination: float = Field(default=0.05, gt=0, lt=0.5)
    train_ratio: float = Field(default=0.8, ge=0.5, lt=1.0)


class RetrainResponse(BaseModel):
    accepted: bool
    message: str
    candidate_version: str
    candidate_path: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    metric_deltas: dict[str, float] = Field(default_factory=dict)


class RejectCandidateRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class RetrainingFromInfluxRequest(BaseModel):
    sensorIds: list[str] | None = None
    periodType: Literal["last_30_days", "last_complete_month", "last_60_days", "last_two_complete_months", "custom"] = "last_complete_month"
    periodStart: datetime | None = None
    periodEnd: datetime | None = None
    format: Literal["parquet", "csv"] = "parquet"
    useFeedback: bool = False


class RetrainingPeriod(BaseModel):
    start: datetime
    end: datetime


class RetrainingFromInfluxResponse(BaseModel):
    jobId: int
    status: str
    period: RetrainingPeriod
    sensorIds: list[str]


class RetrainingExportSummary(BaseModel):
    jobId: int
    status: str
    sourcePath: str | None = None
    reportPath: str | None = None
    period: RetrainingPeriod
    sensorIds: list[str]
    readings: int
    completeDays: int
    expectedIntervals: int
    missingIntervals: int
    duplicates: int
    sensorErrors: int
    zeroFlowPercentage: float
    totalVolume: float
    fileSha256: str | None = None
    fileSizeBytes: int
    trainingAllowed: bool
    blockingReasons: list[str] = Field(default_factory=list)


class PromotionDecisionRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=1000)
    acknowledgedWarnings: bool = False



