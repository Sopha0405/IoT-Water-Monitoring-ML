from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
from influxdb_client import InfluxDBClient
from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.postgres import Base
from app.modules.ml_analysis.data.common import LOCAL_TIMEZONE, SAMPLE_SECONDS, add_interval_columns, normalize_reading_columns
from app.modules.ml_analysis.data.io import sha256_file, write_dataframe, write_json
from app.modules.ml_analysis.features.constants import FEATURE_NAMES, FEATURE_SCHEMA_VERSION
from app.modules.ml_analysis.inference.model import ACTIVE_MODEL_PATH, CANDIDATE_MODEL_PATH, METADATA_PATH

RETRAINING_ROOT = Path("/app/data/retraining/jobs")
RECOMMENDATION_RULES_VERSION = "2026-07-26.v1"
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


def prepare_from_influx(sensor_ids: list[str] | None, period_type: str, output_format: str) -> dict[str, Any]:
    period_start, period_end = calculate_period(period_type)
    job_id = next_job_id()
    source_dir = job_dir(job_id) / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    extension = "csv" if output_format == "csv" else "parquet"
    source_path = source_dir / f"readings.{extension}"
    report_path = source_dir / "export_report.json"

    frame = query_influx_dataframe(period_start, period_end, sensor_ids)
    if not frame.empty:
        frame = frame.sort_values(["sensor_id", "timestamp"])
    write_dataframe(frame, source_path)
    report = build_export_report(
        frame=frame,
        source_path=source_path,
        period_start=period_start,
        period_end=period_end,
        requested_sensor_ids=sensor_ids,
        status="validating_export",
    )
    write_json(report_path, report)
    return {
        "jobId": job_id,
        "status": "ready_to_train" if report["training_allowed"] else "validating_export",
        "period": {"start": period_start, "end": period_end},
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

    first_of_current = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    previous_month_end = first_of_current - timedelta(microseconds=1)
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
    return {
        "jobId": job_id,
        "status": "ready_to_train" if report.get("training_allowed") else "validating_export",
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
    return {
        "status": status,
        "input_path": str(source_path),
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "sensors": sensors or requested_sensor_ids or [],
        "rows": rows,
        "days": max(0, (period_end.date() - period_start.date()).days + 1),
        "complete_days": valid_days,
        "expected_intervals": expected,
        "missing_intervals": missing,
        "duplicates": duplicate_count,
        "sensor_errors": sensor_errors,
        "negative_flow": negative_count,
        "zero_flow_percentage": zero_pct,
        "total_volume_liters": total_volume,
        "sha256": sha256_file(source_path) if source_path.exists() else None,
        "file_size_bytes": source_path.stat().st_size if source_path.exists() else 0,
        "training_allowed": not blocking,
        "blocking_reasons": blocking,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


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
