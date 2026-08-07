from __future__ import annotations

import json
import threading
import time as time_module
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from influxdb_client import InfluxDBClient
from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.postgres import Base
from app.modules.ml_analysis.data.common import LOCAL_TIMEZONE, SAMPLE_SECONDS, add_interval_columns, normalize_reading_columns
from app.modules.ml_analysis.data.gold import build_gold
from app.modules.ml_analysis.data.io import read_dataframe, sha256_file, write_dataframe, write_json
from app.modules.ml_analysis.data.preparation import prepare_dataset
from app.modules.ml_analysis.data.split import temporal_split
from app.modules.ml_analysis.features.constants import FEATURE_NAMES, FEATURE_SCHEMA_VERSION, PIPELINE_VERSION, WINDOW_SIZE
from app.modules.ml_analysis.inference.model import ACTIVE_MODEL_PATH, CANDIDATE_MODEL_PATH, METADATA_PATH
from app.modules.ml_analysis.training.evaluator import evaluate_test
from app.modules.ml_analysis.training.trainer import train_grid

RETRAINING_ROOT = Path("/app/data/retraining/jobs")
PROCESSED_ML_DIR = Path("/app/data/processed/ml")
EVALUATION_ML_DIR = Path("/app/data/evaluation/ml")
RECOMMENDATION_RULES_VERSION = "2026-07-26.v1"
TRAINING_STAGES = [
    ("querying_telemetry", "Consulta de telemetria", "Lecturas obtenidas desde InfluxDB."),
    ("validating", "Validacion de lecturas", "Ordenamiento, duplicados, timestamps y caudal."),
    ("building_windows", "Construccion de ventanas", "Ventanas de 60 lecturas consecutivas por dispositivo."),
    ("extracting_features", "Extraccion de caracteristicas", "Feature set oficial de 24 variables."),
    ("splitting", "Preparacion de subconjuntos temporales", "Split temporal sin fuga de informacion futura."),
    ("integrating_feedback", "Integracion de retroalimentacion", "Uso como evidencia de evaluacion humana cuando exista."),
    ("training", "Entrenamiento", "Isolation Forest genera candidate.joblib."),
    ("evaluating", "Evaluacion", "Evaluacion del candidato sobre test temporal."),
    ("generating_candidate", "Generacion del candidato", "Validacion de archivo, schema y prediccion de prueba."),
    ("comparing", "Comparacion con activo", "Comparacion contra active.joblib y recomendacion tecnica."),
]
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
_training_lock = threading.Lock()
LEAK_TYPE_TARGETS = {
    "fuga_sostenida": {"minimum_recall": 0.80},
    "consumo_creciente": {"minimum_recall": 0.75},
    "pico_anomalo": {"minimum_event_recall": 0.80},
    "microfuga": {"minimum_recall": 0.0, "configurable": True},
}


class MLRecommendationHistory(Base):
    __tablename__ = "ml_recommendation_history"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    job_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    recommendation: Mapped[str] = mapped_column(String(80), nullable=False)
    recommendation_reasons: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    blocking_reasons: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    metrics_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recommendation_rules_version: Mapped[str] = mapped_column(String(80), nullable=False)
    promotion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def prepare_from_influx(
    sensor_ids: list[str] | None,
    period_type: str,
    output_format: str,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    use_feedback: bool = False,
) -> dict[str, Any]:
    if period_type == "custom":
        if period_start is None or period_end is None:
            raise ValueError("periodStart y periodEnd son obligatorios para rango personalizado")
        selected_start, selected_end = period_start, period_end
    else:
        selected_start, selected_end = calculate_period(period_type)
    job_id = next_job_id()
    source_dir = job_dir(job_id) / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    extension = "csv" if output_format == "csv" else "parquet"
    source_path = source_dir / f"readings.{extension}"
    report_path = source_dir / "export_report.json"

    frame = query_influx_dataframe(selected_start, selected_end, sensor_ids)
    if not frame.empty:
        frame = frame.sort_values(["sensor_id", "timestamp"])
    write_dataframe(frame, source_path)
    report = build_export_report(
        frame=frame,
        source_path=source_path,
        period_start=selected_start,
        period_end=selected_end,
        requested_sensor_ids=sensor_ids,
        status="validating_export",
        use_feedback=use_feedback,
    )
    write_json(report_path, report)
    _write_job_state(
        job_id,
        {
            "job_id": job_id,
            "jobId": job_id,
            "status": "queued" if report["training_allowed"] else "validating_export",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "dataset_id": report["dataset_id"],
            "source": report["source"],
            "period": {"start": report["period_start"], "end": report["period_end"]},
            "sensorIds": report["sensors"],
            "steps": _initial_steps({"querying_telemetry": {"count": report["raw_readings"]}}),
            "summary": report,
        },
    )
    return {
        "jobId": job_id,
        "status": "queued" if report["training_allowed"] else "validating_export",
        "period": {"start": selected_start, "end": selected_end},
        "sensorIds": report["sensors"],
    }


def calculate_period(period_type: str, now: datetime | None = None) -> tuple[datetime, datetime]:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    if period_type == "last_60_days":
        end = current
        start = end - timedelta(days=60)
        return start, end
    if period_type == "last_30_days":
        end = current
        start = end - timedelta(days=30)
        return start, end

    first_of_current = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    previous_month_end = first_of_current - timedelta(microseconds=1)
    if period_type == "last_complete_month":
        start = previous_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, previous_month_end
    start_month = previous_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start_month.month == 1:
        start = start_month.replace(year=start_month.year - 1, month=12)
    else:
        start = start_month.replace(month=start_month.month - 1)
    return start, previous_month_end


def next_job_id() -> int:
    RETRAINING_ROOT.mkdir(parents=True, exist_ok=True)
    ids = [int(path.name) for path in RETRAINING_ROOT.iterdir() if path.is_dir() and path.name.isdigit()]
    return max(ids, default=0) + 1


def job_dir(job_id: int) -> Path:
    return RETRAINING_ROOT / str(job_id)


def source_file(job_id: int) -> Path:
    source = job_dir(job_id) / "source"
    for name in ["readings.parquet", "readings.csv"]:
        candidate = source / name
        if candidate.exists():
            return candidate
    raise FileNotFoundError("No existe dataset exportado para el trabajo.")


def export_report_path(job_id: int) -> Path:
    return job_dir(job_id) / "source" / "export_report.json"


def load_export_summary(job_id: int) -> dict[str, Any]:
    path = export_report_path(job_id)
    if not path.exists():
        raise FileNotFoundError("No existe resumen de exportacion.")
    report = json.loads(path.read_text(encoding="utf-8"))
    state = load_job_state(job_id)
    return {
        "jobId": job_id,
        "status": state.get("status") if state else ("queued" if report.get("training_allowed") else "validating_export"),
        "sourcePath": report.get("input_path"),
        "reportPath": str(path),
        "period": {"start": report["period_start"], "end": report["period_end"]},
        "sensorIds": report.get("sensors", []),
        "readings": int(report.get("rows", 0)),
        "completeDays": int(report.get("complete_days", 0)),
        "expectedIntervals": int(report.get("expected_intervals", 0)),
        "missingIntervals": int(report.get("missing_intervals", 0)),
        "duplicates": int(report.get("duplicates", 0)),
        "sensorErrors": int(report.get("sensor_errors", 0)),
        "zeroFlowPercentage": float(report.get("zero_flow_percentage", 0.0)),
        "totalVolume": float(report.get("total_volume_liters", 0.0)),
        "fileSha256": report.get("sha256"),
        "fileSizeBytes": int(report.get("file_size_bytes", 0)),
        "trainingAllowed": bool(report.get("training_allowed")),
        "blockingReasons": report.get("blocking_reasons", []),
        "datasetId": report.get("dataset_id"),
        "rawReadings": report.get("raw_readings"),
        "validReadings": report.get("valid_readings"),
        "discardedReadings": report.get("discarded_readings"),
        "completeWindows": report.get("complete_windows"),
        "samplingIntervalSeconds": report.get("sampling_interval_seconds"),
        "featureSchemaVersion": report.get("feature_schema_version"),
        "pipelineVersion": report.get("pipeline_version"),
        "steps": state.get("steps", []) if state else [],
        "candidate": state.get("candidate") if state else None,
        "error": state.get("error") if state else None,
    }


def query_influx_dataframe(period_start: datetime, period_end: datetime, sensor_ids: list[str] | None) -> pd.DataFrame:
    if not settings.influx_token:
        return empty_readings_frame()
    filters = [f'r["_measurement"] == "{flux_string(settings.influx_measurement)}"', 'r["_field"] == "flow_lpm"']
    if sensor_ids:
        sensors = "[" + ", ".join(f'"{flux_string(sensor)}"' for sensor in sensor_ids) + "]"
        filters.append(f'contains(value: r["device_id"], set: {sensors})')
    flux = f'''
from(bucket: "{flux_string(settings.influx_bucket)}")
  |> range(start: {period_start.isoformat()}, stop: {period_end.isoformat()})
  |> filter(fn: (r) => {' and '.join(filters)})
  |> keep(columns: ["_time", "_value", "device_id", "site", "floor", "tenant"])
  |> sort(columns: ["_time"], desc: false)
'''
    with InfluxDBClient(url=settings.influx_url, token=settings.influx_token, org=settings.influx_org) as client:
        tables = client.query_api().query(flux, org=settings.influx_org)
    rows = []
    for table in tables:
        for record in table.records:
            values = record.values
            rows.append(
                {
                    "timestamp": record.get_time(),
                    "sensor_id": values.get("device_id"),
                    "flow_lpm": float(record.get_value()),
                    "site": values.get("site"),
                    "floor": values.get("floor"),
                    "tenant": values.get("tenant"),
                    "status": "ok",
                }
            )
    return pd.DataFrame(rows, columns=empty_readings_frame().columns)


def empty_readings_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["timestamp", "sensor_id", "flow_lpm", "site", "floor", "tenant", "status"])


def build_export_report(
    *,
    frame: pd.DataFrame,
    source_path: Path,
    period_start: datetime,
    period_end: datetime,
    requested_sensor_ids: list[str] | None,
    status: str,
    use_feedback: bool = False,
) -> dict[str, Any]:
    normalized = normalize_reading_columns(frame) if not frame.empty else empty_readings_frame()
    if not normalized.empty:
        normalized = add_interval_columns(normalized)
    sensors = sorted(normalized["sensor_id"].dropna().astype(str).unique().tolist()) if "sensor_id" in normalized else []
    period_seconds = max(0.0, (period_end - period_start).total_seconds())
    expected_per_sensor = int(period_seconds // SAMPLE_SECONDS)
    expected = expected_per_sensor * max(1, len(sensors or requested_sensor_ids or []))
    rows = int(len(normalized))
    missing = max(0, expected - rows)
    expected_ratio = rows / expected if expected else 0.0
    clean = normalized.loc[~normalized.get("status", pd.Series(dtype=str)).isin({"sensor_error", "desconectado", "error_lectura", "offline", "maintenance", "mantenimiento"})] if rows else normalized
    valid_days = int(clean.assign(local_date=pd.to_datetime(clean["timestamp"], utc=True).dt.tz_convert(LOCAL_TIMEZONE).dt.date).groupby(["sensor_id", "local_date"]).size().ge(int(0.8 * 24 * 60 * 60 / SAMPLE_SECONDS)).sum()) if rows else 0
    duplicate_count = int(normalized.duplicated(["sensor_id", "timestamp"], keep=False).sum()) if rows else 0
    negative_count = int(normalized["flow_lpm"].lt(0).sum()) if rows else 0
    sensor_errors = int(normalized["status"].isin({"sensor_error", "desconectado", "error_lectura", "offline", "maintenance", "mantenimiento"}).sum()) if rows else 0
    invalid_flow = int(normalized["flow_lpm"].isna().sum() + normalized["flow_lpm"].lt(0).sum()) if rows else 0
    valid_mask = (
        normalized["timestamp"].notna()
        & normalized["sensor_id"].astype("string").ne("")
        & normalized["flow_lpm"].notna()
        & np.isfinite(normalized["flow_lpm"].to_numpy(dtype=float, na_value=np.nan))
        & normalized["flow_lpm"].ge(0)
        & ~normalized["is_duplicate"].fillna(False)
        & ~normalized["status"].isin({"sensor_error", "desconectado", "error_lectura", "offline", "maintenance", "mantenimiento"})
    ) if rows else pd.Series(dtype=bool)
    valid_readings = int(valid_mask.sum()) if rows else 0
    discarded_readings = int(rows - valid_readings)
    complete_windows, gaps = continuity_window_summary(normalized.loc[valid_mask].copy() if rows else normalized)
    total_volume = float(normalized["flow_lpm"].clip(lower=0).sum() * SAMPLE_SECONDS / 60.0) if rows else 0.0
    zero_pct = float(normalized["flow_lpm"].fillna(0).le(0.03).mean()) if rows else 0.0
    blocking = []
    if valid_days < 30:
        blocking.append("minimo_30_dias_validos_no_cumplido")
    if expected_ratio < 0.80:
        blocking.append("menos_del_80_por_ciento_de_lecturas_esperadas")
    if duplicate_count:
        blocking.append("timestamps_duplicados_criticos")
    if negative_count:
        blocking.append("caudales_negativos")
    if rows == 0:
        blocking.append("sin_lecturas_exportadas_desde_influx")
    if len(clean) < int(30 * 24 * 60 * 60 / SAMPLE_SECONDS):
        blocking.append("normalidad_limpia_insuficiente")
    if complete_windows == 0:
        blocking.append("sin_ventanas_validas_de_60_lecturas")
    dataset_id = f"influx-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{sha256_file(source_path)[:8] if source_path.exists() else 'pending'}"
    return {
        "dataset_id": dataset_id,
        "status": status,
        "input_path": str(source_path),
        "source": "InfluxDB",
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "sensors": sensors or requested_sensor_ids or [],
        "devices": sensors or requested_sensor_ids or [],
        "sampling_interval_seconds": SAMPLE_SECONDS,
        "raw_readings": rows,
        "valid_readings": valid_readings,
        "discarded_readings": discarded_readings,
        "complete_windows": complete_windows,
        "window_size": WINDOW_SIZE,
        "features_count": len(FEATURE_NAMES),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "pipeline_version": PIPELINE_VERSION,
        "missing_groups": gaps,
        "use_feedback": use_feedback,
        "rows": rows,
        "days": max(0, (period_end.date() - period_start.date()).days + 1),
        "complete_days": valid_days,
        "expected_intervals": expected,
        "missing_intervals": missing,
        "duplicates": duplicate_count,
        "sensor_errors": sensor_errors,
        "negative_flow": negative_count,
        "invalid_flow": invalid_flow,
        "zero_flow_percentage": zero_pct,
        "total_volume_liters": total_volume,
        "sha256": sha256_file(source_path) if source_path.exists() else None,
        "file_size_bytes": source_path.stat().st_size if source_path.exists() else 0,
        "training_allowed": not blocking,
        "blocking_reasons": blocking,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def continuity_window_summary(frame: pd.DataFrame) -> tuple[int, list[dict[str, Any]]]:
    if frame.empty:
        return 0, []
    total_windows = 0
    gaps: list[dict[str, Any]] = []
    frame = add_interval_columns(frame.sort_values(["sensor_id", "timestamp"]))
    for sensor_id, sensor_frame in frame.groupby("sensor_id", sort=True):
        segment_length = 0
        for _, row in sensor_frame.iterrows():
            interval = row.get("interval_seconds")
            if pd.isna(interval):
                segment_length = 1
                continue
            if abs(float(interval) - SAMPLE_SECONDS) <= 1:
                segment_length += 1
            else:
                if segment_length >= WINDOW_SIZE:
                    total_windows += segment_length // WINDOW_SIZE
                gaps.append(
                    {
                        "sensor_id": str(sensor_id),
                        "timestamp": row["timestamp"].isoformat() if hasattr(row["timestamp"], "isoformat") else str(row["timestamp"]),
                        "interval_seconds": float(interval),
                    }
                )
                segment_length = 1
        if segment_length >= WINDOW_SIZE:
            total_windows += segment_length // WINDOW_SIZE
    return int(total_windows), gaps[:200]


def recommendation_for_job(job_id: int) -> dict[str, Any]:
    frozen = job_dir(job_id) / "recommendation.json"
    if frozen.exists():
        return json.loads(frozen.read_text(encoding="utf-8"))
    payload = generate_recommendation(job_id)
    write_json(frozen, payload)
    return payload


def generate_recommendation(job_id: int) -> dict[str, Any]:
    blocking: list[str] = []
    warnings: list[str] = []
    if not CANDIDATE_MODEL_PATH.exists():
        blocking.append("candidate.joblib no existe")
    test_report = Path("/app/data/evaluation/ml/test_report.json")
    if not test_report.exists():
        blocking.append("evaluacion de test no finalizada")
        report = {}
    else:
        report = json.loads(test_report.read_text(encoding="utf-8"))
    artifact = _load_candidate_artifact(blocking)
    metrics = report.get("test_metrics") or report.get("window_metrics") or {}
    active_metrics = _load_active_metrics()
    if CANDIDATE_MODEL_PATH.exists() and report.get("model_sha256") != sha256_file(CANDIDATE_MODEL_PATH):
        blocking.append("hash del candidato no coincide con el reporte")
    if artifact and (artifact.get("feature_schema_version") != FEATURE_SCHEMA_VERSION or artifact.get("feature_names") != FEATURE_NAMES):
        blocking.append("esquema de features incompatible")
    if report.get("test_used_for_selection") is not False:
        blocking.append("test_used_for_selection debe ser false")
    if artifact and report and report.get("threshold") != artifact.get("threshold"):
        blocking.append("threshold no aprobado")
    _minimum_metric(metrics, "precision", 0.80, blocking)
    _minimum_metric(metrics, "recall", 0.60, blocking)
    if _metric(metrics, "fpr", 1.0) > 0.02:
        blocking.append("FPR demasiado alto")
    if not ACTIVE_MODEL_PATH.exists():
        warnings.append("active.joblib no existe para comparacion completa")

    deltas = metric_deltas(metrics, active_metrics)
    type_comparison = leak_type_comparison(report, active_metrics)
    add_type_warnings(type_comparison, report, warnings)
    recommendation = "promotion_blocked" if blocking else classify_recommendation(metrics, active_metrics, deltas, warnings, report)
    title = {
        "promote_recommended": "Se recomienda promover el candidato",
        "keep_active_recommended": "El modelo activo sigue siendo la mejor opcion",
        "manual_review_required": "Requiere revision manual",
        "promotion_blocked": "Promocion bloqueada",
    }[recommendation]
    positive = positive_reasons(deltas, metrics)
    payload = {
        "jobId": job_id,
        "recommendation": recommendation,
        "title": title,
        "summary": summary_text(recommendation),
        "confidenceLevel": "high" if recommendation in {"promote_recommended", "promotion_blocked"} else "medium",
        "blockingReasons": blocking,
        "positiveReasons": positive,
        "warnings": warnings,
        "metricDeltas": deltas,
        "metricsSnapshot": {"candidate": metrics, "active": active_metrics},
        "typeComparison": type_comparison,
        "recommendationRulesVersion": RECOMMENDATION_RULES_VERSION,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }
    return payload


def _load_candidate_artifact(blocking: list[str]) -> dict[str, Any] | None:
    if not CANDIDATE_MODEL_PATH.exists():
        return None
    try:
        artifact = joblib.load(CANDIDATE_MODEL_PATH)
    except Exception:
        blocking.append("candidate.joblib invalido")
        return None
    return artifact if isinstance(artifact, dict) else getattr(artifact, "__dict__", {})


def _load_active_metrics() -> dict[str, Any]:
    if not METADATA_PATH.exists():
        return {}
    try:
        payload = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload.get("metrics", {}) if isinstance(payload, dict) else {}


def _metric(metrics: dict[str, Any], name: str, default: float = 0.0) -> float:
    value = metrics.get(name)
    return float(value) if isinstance(value, (int, float)) else default


def _minimum_metric(metrics: dict[str, Any], name: str, minimum: float, blocking: list[str]) -> None:
    if _metric(metrics, name, -1.0) < minimum:
        blocking.append(f"{name.capitalize()} insuficiente")


def metric_deltas(candidate: dict[str, Any], active: dict[str, Any]) -> dict[str, float]:
    names = ["precision", "recall", "f1", "f0_5", "fpr", "pr_auc", "roc_auc", "event_recall", "latency_per_sample_ms"]
    out = {}
    for name in names:
        if isinstance(candidate.get(name), (int, float)) and isinstance(active.get(name), (int, float)):
            out[name] = round(float(candidate[name]) - float(active[name]), 6)
    return out


def classify_recommendation(metrics: dict[str, Any], active: dict[str, Any], deltas: dict[str, float], warnings: list[str], report: dict[str, Any]) -> str:
    f1 = deltas.get("f1", 0.0)
    recall = deltas.get("recall", 0.0)
    precision = deltas.get("precision", 0.0)
    fpr = deltas.get("fpr", 0.0)
    false_alerts = deltas.get("false_alerts_per_day", 0.0)
    if report.get("dataset_warning") or "periods_differ" in report:
        return "manual_review_required"
    if (f1 >= 0.02 and fpr <= 0.002) or (recall >= 0.05 and precision >= -0.02 and _metric(metrics, "fpr") <= 0.02) or (fpr <= -0.005 and recall >= -0.02):
        return "manual_review_required" if warnings else "promote_recommended"
    if false_alerts > 0 or deltas.get("latency_per_sample_ms", 0.0) > 5:
        return "keep_active_recommended"
    return "keep_active_recommended"


def leak_type_comparison(report: dict[str, Any], active_metrics: dict[str, Any]) -> list[dict[str, Any]]:
    candidate = report.get("recall_by_type", {}) if isinstance(report, dict) else {}
    active_by_type = active_metrics.get("recall_by_type", {}) if isinstance(active_metrics, dict) else {}
    rows = []
    for leak_type, targets in LEAK_TYPE_TARGETS.items():
        c_value = candidate.get(leak_type)
        a_value = active_by_type.get(leak_type)
        rows.append(
            {
                "type": leak_type,
                "candidateRecall": c_value,
                "activeRecall": a_value,
                "delta": round(float(c_value) - float(a_value), 6) if isinstance(c_value, (int, float)) and isinstance(a_value, (int, float)) else None,
                "targets": targets,
            }
        )
    rows.append({"type": "normales_dificiles", "candidateFpr": (report.get("normal_difficult") or {}).get("fpr"), "activeFpr": (active_metrics.get("normal_difficult") or {}).get("fpr")})
    return rows


def add_type_warnings(type_rows: list[dict[str, Any]], report: dict[str, Any], warnings: list[str]) -> None:
    for row in type_rows:
        if row.get("type") == "microfuga" and row.get("candidateRecall") == 0:
            warnings.append("Recall de microfugas igual a 0")
        if isinstance(row.get("delta"), (int, float)) and row["delta"] < -0.10:
            warnings.append(f"{row['type']} cae mas de 0.10")
        if row.get("type") == "normales_dificiles" and isinstance(row.get("candidateFpr"), (int, float)) and row["candidateFpr"] > 0.10:
            warnings.append("Normales dificiles con FPR mayor a 0.10")
    incidents = report.get("incidents") if isinstance(report, dict) else None
    if isinstance(incidents, dict) and incidents.get("incident_recall", 1.0) < 0.60:
        warnings.append("Recall por evento disminuye o queda bajo objetivo")


def positive_reasons(deltas: dict[str, float], metrics: dict[str, Any]) -> list[str]:
    reasons = []
    if _metric(metrics, "precision") >= 0.80:
        reasons.append("Precision de test igual o superior a 0.80")
    if deltas.get("recall", 0.0) > 0:
        reasons.append(f"Recall de test mejoro en {deltas['recall'] * 100:.1f} puntos porcentuales")
    if deltas.get("fpr", 0.0) < 0:
        reasons.append("FPR disminuyo frente al modelo activo")
    if not reasons:
        reasons.append("El candidato cumple los minimos tecnicos evaluados")
    return reasons


def summary_text(recommendation: str) -> str:
    if recommendation == "promote_recommended":
        return "El candidato mejora metricas relevantes y mantiene los limites operativos requeridos."
    if recommendation == "keep_active_recommended":
        return "El candidato cumple minimos, pero no muestra mejora material suficiente frente al activo."
    if recommendation == "manual_review_required":
        return "Los resultados son mixtos y requieren revision explicita de un administrador."
    return "No se puede promover hasta resolver las razones de bloqueo."


def flux_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def job_state_path(job_id: int) -> Path:
    return job_dir(job_id) / "job_status.json"


def load_job_state(job_id: int) -> dict[str, Any] | None:
    path = job_state_path(job_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_job_state(job_id: int, state: dict[str, Any]) -> None:
    path = job_state_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, state)


def _initial_steps(results: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    results = results or {}
    steps = []
    for key, name, description in TRAINING_STAGES:
        completed = key in results
        steps.append(
            {
                "key": key,
                "name": name,
                "description": description,
                "status": "completed" if completed else "pending",
                "started_at": None,
                "finished_at": None,
                "duration_seconds": None,
                "result": results.get(key),
                "warnings": [],
                "error": None,
            }
        )
    return steps


def _update_step(job_id: int, key: str, *, status: str, result: dict[str, Any] | None = None, error: str | None = None, warnings: list[str] | None = None) -> None:
    state = load_job_state(job_id) or {"job_id": job_id, "jobId": job_id, "steps": _initial_steps()}
    now = datetime.now(timezone.utc).isoformat()
    for step in state["steps"]:
        if step["key"] != key:
            continue
        if status in {"running", "completed", "warning", "failed"} and not step.get("started_at"):
            step["started_at"] = now
        if status in {"completed", "warning", "failed"}:
            step["finished_at"] = now
            if step.get("started_at"):
                start = datetime.fromisoformat(str(step["started_at"]).replace("Z", "+00:00"))
                end = datetime.fromisoformat(now)
                step["duration_seconds"] = round((end - start).total_seconds(), 3)
        step["status"] = status
        if result is not None:
            step["result"] = result
        if warnings is not None:
            step["warnings"] = warnings
        if error is not None:
            step["error"] = error
    completed = sum(1 for step in state["steps"] if step["status"] in {"completed", "warning"})
    state["completed_steps"] = completed
    state["total_steps"] = len(state["steps"])
    state["currentStep"] = key
    state["updated_at"] = now
    _write_job_state(job_id, state)


def _set_job_status(job_id: int, status: str, **updates: Any) -> None:
    state = load_job_state(job_id) or {"job_id": job_id, "jobId": job_id, "steps": _initial_steps()}
    state.update(updates)
    state["status"] = status
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_job_state(job_id, state)


def start_training_job(job_id: int) -> dict[str, Any]:
    state = load_job_state(job_id)
    if state and state.get("status") not in TERMINAL_STATUSES and state.get("status") not in {"queued", "validating_export"}:
        return state
    if not _training_lock.acquire(blocking=False):
        raise RuntimeError("Ya existe un entrenamiento en ejecucion.")
    _set_job_status(job_id, "queued", queued_at=datetime.now(timezone.utc).isoformat())
    thread = threading.Thread(target=_run_training_job, args=(job_id,), daemon=True)
    thread.start()
    return load_job_state(job_id) or {"jobId": job_id, "status": "queued"}


def _run_training_job(job_id: int) -> None:
    started = time_module.perf_counter()
    try:
        _set_job_status(job_id, "preparing_data", started_at=datetime.now(timezone.utc).isoformat())
        source = source_file(job_id)
        job = job_dir(job_id)
        processed = job / "processed"
        evaluation = job / "evaluation"
        processed.mkdir(parents=True, exist_ok=True)
        evaluation.mkdir(parents=True, exist_ok=True)

        export_report = json.loads(export_report_path(job_id).read_text(encoding="utf-8"))
        _update_step(job_id, "querying_telemetry", status="completed", result={"count": export_report.get("raw_readings"), "source": "InfluxDB"})

        _set_job_status(job_id, "validating")
        clean_path = processed / "readings_clean.parquet"
        cleaning_report_path = processed / "cleaning_report.json"
        _update_step(job_id, "validating", status="running")
        cleaning_report = prepare_dataset(source, clean_path, cleaning_report_path)
        _update_step(job_id, "validating", status="completed", result={"valid_readings": cleaning_report.get("clean_rows"), "discarded_readings": cleaning_report.get("excluded_rows")})

        _set_job_status(job_id, "building_windows")
        gold_path = processed / "windows_gold.parquet"
        gold_report_path = processed / "gold_report.json"
        _update_step(job_id, "building_windows", status="running")
        gold_report = build_gold(clean_path, gold_path, gold_report_path)
        if int(gold_report.get("windows", 0)) <= 0:
            raise RuntimeError("No se encontraron suficientes lecturas consecutivas para construir ventanas de cinco minutos.")
        _update_step(job_id, "building_windows", status="completed", result={"complete_windows": gold_report.get("windows"), "discarded_windows": gold_report.get("discarded_windows")})
        _update_step(job_id, "extracting_features", status="completed", result={"features_count": len(FEATURE_NAMES), "feature_names": FEATURE_NAMES, "feature_schema_version": FEATURE_SCHEMA_VERSION, "pipeline_version": PIPELINE_VERSION})

        _set_job_status(job_id, "splitting")
        split_dir = processed / "splits"
        _update_step(job_id, "splitting", status="running")
        split_report = temporal_split(gold_path, split_dir)
        _update_step(job_id, "splitting", status="completed", result={"rows": split_report.get("rows"), "ratios": split_report.get("ratios")})
        _update_step(job_id, "integrating_feedback", status="completed", result={"policy": "feedback aprobado se usa como evidencia; Isolation Forest permanece no supervisado", "used_feedback": bool(export_report.get("use_feedback"))})

        _set_job_status(job_id, "training")
        training_report_path = evaluation / "training_report.json"
        _update_step(job_id, "training", status="running")
        training_report = train_grid(
            split_dir / "train.parquet",
            split_dir / "validation.parquet",
            CANDIDATE_MODEL_PATH,
            training_report_path,
            allow_fallback=True,
        )
        EVALUATION_ML_DIR.mkdir(parents=True, exist_ok=True)
        write_json(EVALUATION_ML_DIR / "training_report.json", training_report)
        if not training_report.get("model_saved"):
            raise RuntimeError(training_report.get("failure_reason") or "No se genero candidate.joblib")
        _update_step(job_id, "training", status="completed", result={"candidate_sha256": training_report.get("candidate_sha256"), "metrics": (training_report.get("approved_candidate") or {}).get("metrics")})

        _set_job_status(job_id, "evaluating")
        test_report_path = evaluation / "test_report.json"
        predictions_path = evaluation / "test_predictions.parquet"
        _update_step(job_id, "evaluating", status="running")
        try:
            test_report = evaluate_test(CANDIDATE_MODEL_PATH, split_dir / "test.parquet", predictions_path, test_report_path)
            write_json(EVALUATION_ML_DIR / "test_report.json", test_report)
            _update_step(job_id, "evaluating", status="completed", result={"metrics": test_report.get("test_metrics"), "report_path": str(test_report_path)})
        except Exception as exc:
            test_report = {"metrics_unavailable_reason": str(exc), "test_report_path": str(test_report_path)}
            write_json(test_report_path, test_report)
            write_json(EVALUATION_ML_DIR / "test_report.json", test_report)
            _update_step(job_id, "evaluating", status="warning", result={"metrics": "No disponible", "reason": str(exc)}, warnings=[str(exc)])

        _set_job_status(job_id, "generating_candidate")
        _update_step(job_id, "generating_candidate", status="running")
        candidate_summary = validate_candidate_artifact(CANDIDATE_MODEL_PATH)
        _update_step(job_id, "generating_candidate", status="completed", result=candidate_summary)

        _set_job_status(job_id, "comparing")
        _update_step(job_id, "comparing", status="running")
        recommendation = generate_recommendation(job_id)
        _update_step(job_id, "comparing", status="completed", result={"recommendation": recommendation.get("recommendation"), "metricDeltas": recommendation.get("metricDeltas")})

        _set_job_status(
            job_id,
            "completed",
            finished_at=datetime.now(timezone.utc).isoformat(),
            duration_seconds=round(time_module.perf_counter() - started, 3),
            candidate=candidate_summary,
            recommendation=recommendation,
            artifacts={
                "source": str(source),
                "clean": str(clean_path),
                "gold": str(gold_path),
                "splits": str(split_dir),
                "training_report": str(training_report_path),
                "test_report": str(test_report_path),
                "candidate": str(CANDIDATE_MODEL_PATH),
            },
        )
    except Exception as exc:
        _set_job_status(job_id, "failed", error=str(exc), finished_at=datetime.now(timezone.utc).isoformat())
        current = (load_job_state(job_id) or {}).get("currentStep")
        if current:
            _update_step(job_id, current, status="failed", error=str(exc))
    finally:
        if _training_lock.locked():
            _training_lock.release()


def validate_candidate_artifact(path: str | Path) -> dict[str, Any]:
    candidate_path = Path(path)
    if not candidate_path.exists():
        raise RuntimeError("candidate.joblib no existe")
    artifact = joblib.load(candidate_path)
    if not isinstance(artifact, dict):
        raise RuntimeError("candidate.joblib corrupto: se esperaba un diccionario")
    if artifact.get("feature_names") != FEATURE_NAMES:
        raise RuntimeError("candidate.joblib incompatible: orden de features distinto")
    if artifact.get("feature_schema_version") != FEATURE_SCHEMA_VERSION:
        raise RuntimeError("candidate.joblib incompatible: feature_schema_version distinto")
    model = artifact.get("model")
    scaler = artifact.get("scaler")
    if model is None or scaler is None:
        raise RuntimeError("candidate.joblib no contiene model/scaler")
    probe = np.zeros((1, len(FEATURE_NAMES)), dtype=float)
    _ = model.decision_function(scaler.transform(probe))
    return {
        "candidate_id": sha256_file(candidate_path)[:16],
        "version": artifact.get("candidate_version") or artifact.get("version") or artifact.get("trained_at"),
        "status": "candidate",
        "path": str(candidate_path),
        "sha256": sha256_file(candidate_path),
        "file_size_bytes": candidate_path.stat().st_size,
        "trained_at": artifact.get("trained_at"),
        "feature_schema_version": artifact.get("feature_schema_version"),
        "pipeline_version": artifact.get("artifact_version"),
        "features_count": len(artifact.get("feature_names") or []),
        "feature_names": artifact.get("feature_names"),
        "hyperparameters": artifact.get("hyperparameters"),
        "contamination": (artifact.get("hyperparameters") or {}).get("contamination"),
        "threshold": artifact.get("threshold"),
        "metrics": artifact.get("metrics") or {},
        "test_prediction_ok": True,
    }
