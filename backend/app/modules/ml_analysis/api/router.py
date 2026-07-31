from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.postgres import get_db
from app.modules.devices.model import Device
from app.modules.ml_analysis.inference.isolation_forest import IsolationForestModel
from app.modules.ml_analysis.inference.model import ACTIVE_MODEL_PATH, MLAnalysis, ModelManager
from app.modules.ml_analysis.api.schemas import (
    DriftReport,
    InferenceRequest,
    InferenceResponse,
    ModelStatus,
    RejectCandidateRequest,
    RetrainingExportSummary,
    RetrainingFromInfluxRequest,
    RetrainingFromInfluxResponse,
    RetrainRequest,
    RetrainResponse,
)
from app.modules.ml_analysis.inference.service import (
    clear_model_cache,
    compute_drift,
    get_last_drift_report,
    persist_inference_result,
    run_inference,
)
from app.modules.ml_analysis.training.admin_retraining import (
    RETRAINING_ROOT,
    export_report_path,
    load_export_summary,
    prepare_from_influx,
    recommendation_for_job,
    source_file,
)
from app.modules.roles.model import Role
from app.modules.users.model import User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ml"])
model_manager = ModelManager()
PROCESSED_DATA_DIR = Path("/app/data/processed").resolve()


def require_role(*role_names: str):
    """Valida roles sin acceder a role.name cuando el rol no existe."""
    normalized = {name.strip().lower() for name in role_names}

    def dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        role = db.query(Role).filter(Role.id == current_user.role_id).first()
        if role is None or role.name.strip().lower() not in normalized:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Rol no autorizado.",
            )
        return current_user

    return dependency


admin_router = APIRouter(
    prefix="/api/v1/admin/ml/retraining",
    tags=["admin-ml-retraining"],
)


@router.get("/")
async def list_ml_analysis(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lista resultados ML guardados para la pantalla de alertas."""
    del current_user
    rows = (
        db.query(MLAnalysis)
        .order_by(MLAnalysis.processed_at.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": row.id,
            "alert_id": row.alert_id,
            "device_id": row.device_id,
            "floor": row.floor,
            "observed_value": row.observed_value,
            "model_name": row.model_name,
            "raw_anomaly_score": row.anomaly_score,
            "anomaly_score": row.confidence if row.prediction == "anomaly" else 0,
            "prediction": row.prediction,
            "confidence": row.confidence,
            "processed_at": row.processed_at,
        }
        for row in rows
    ]


@router.post("/run")
async def run_analysis_for_active_devices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ejecuta inferencia para los dispositivos activos registrados."""
    del current_user
    devices = (
        db.query(Device)
        .filter(Device.status == "active")
        .order_by(Device.device_id.asc())
        .all()
    )
    if not devices:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay sensores activos para analizar.",
        )

    results = []
    anomalies = 0
    errors = []
    for device in devices:
        try:
            result = await run_inference(device.device_id)
            alert = await persist_inference_result(result, db)
            if result.prediction == "anomaly":
                anomalies += 1
            results.append(
                {
                    "sensor_id": result.sensor_id,
                    "prediction": result.prediction,
                    "severity": result.severity,
                    "confidence": result.confidence,
                    "alert_id": alert.id if alert is not None else None,
                }
            )
        except (RuntimeError, ValueError) as exc:
            errors.append({"sensor_id": device.device_id, "detail": str(exc)})

    return {
        "processed": len(results),
        "anomalies": anomalies,
        "errors": errors,
        "results": results,
    }


@router.post("/analyze", response_model=InferenceResponse)
async def analyze_sensor(
    request: InferenceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Infiere sobre 60 lecturas, registra el anÃ¡lisis y alerta si corresponde."""
    del current_user
    try:
        result = await run_inference(request.sensor_id)
        await persist_inference_result(result, db)
        return result
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


@router.get("/status", response_model=ModelStatus)
async def status_model(current_user: User = Depends(get_current_user)):
    del current_user
    return model_manager.get_status()


@router.get("/admin/status")
async def admin_model_status(
    current_user: User = Depends(require_role("supervisor", "ti", "admin")),
):
    del current_user
    payload = model_manager.get_model_status()
    payload["retraining_jobs"] = _collect_retraining_jobs()
    return payload


@router.get("/drift", response_model=DriftReport)
async def drift_report(
    current_user: User = Depends(require_role("supervisor", "ti", "admin")),
):
    del current_user
    report = get_last_drift_report()
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No existe reporte de drift calculado con datos reales.",
        )
    return report


@router.post("/retrain", response_model=RetrainResponse)
async def retrain_model(
    request: RetrainRequest,
    current_user: User = Depends(require_role("supervisor", "ti", "admin")),
):
    """El entrenamiento oficial se ejecuta por CLI dentro de Docker; no hay reentrenamiento automatico."""
    del request, current_user
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Use python -m app.modules.ml_analysis.cli.train dentro del contenedor backend.",
    )


@router.post("/promote", response_model=ModelStatus)
async def promote_candidate(
    current_user: User = Depends(require_role("supervisor", "ti", "admin")),
):
    """La promocion oficial requiere test-report y se ejecuta por CLI."""
    del current_user
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Use python -m app.modules.ml_analysis.cli.promote_model con --test-report y --confirm.",
    )


@router.post("/reject", response_model=ModelStatus)
async def reject_candidate(
    request: RejectCandidateRequest,
    current_user: User = Depends(require_role("supervisor", "ti", "admin")),
):
    del current_user
    if not model_manager.reject_candidate(request.reason):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No existe candidate.joblib para rechazar.",
        )
    return model_manager.get_status()


@router.post("/rollback", response_model=ModelStatus)
async def rollback_model(
    current_user: User = Depends(require_role("supervisor", "ti", "admin")),
):
    del current_user
    try:
        rolled_back = model_manager.rollback()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    if not rolled_back:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No hay una versiÃ³n activa archivada para rollback.",
        )
    clear_model_cache()
    return model_manager.get_status()


def _validated_processed_path(raw_path: str) -> Path:
    path = Path(raw_path).resolve()
    try:
        path.relative_to(PROCESSED_DATA_DIR)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La ruta debe estar dentro de /app/data/processed.",
        ) from exc
    return path


async def compute_daily_drift(db: Session) -> DriftReport:
    """Compatibilidad para el worker: calcula drift si existe active.joblib."""
    path = Path(ACTIVE_MODEL_PATH)
    if not path.exists():
        raise RuntimeError("No existe active.joblib")
    model = IsolationForestModel.load(path)
    if model.training_data is None:
        raise RuntimeError("El modelo activo no contiene training_data")
    return await compute_drift(model.training_data, model.training_data, db)


@admin_router.post("/from-influx", response_model=RetrainingFromInfluxResponse)
async def prepare_candidate_from_influx(
    request: RetrainingFromInfluxRequest | None = None,
    current_user: User = Depends(require_role("supervisor", "ti", "admin")),
):
    del current_user
    payload = request or RetrainingFromInfluxRequest()
    try:
        return prepare_from_influx(payload.sensorIds, payload.periodType, payload.format)
    except Exception as exc:
        logger.exception("No se pudo preparar dataset desde InfluxDB")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"No se pudo exportar desde InfluxDB: {exc}",
        ) from exc


@admin_router.get("/jobs")
async def list_retraining_jobs(
    current_user: User = Depends(require_role("supervisor", "ti", "admin")),
):
    del current_user
    return _collect_retraining_jobs()


def _collect_retraining_jobs() -> list[dict[str, object]]:
    if not RETRAINING_ROOT.exists():
        return []
    jobs = []
    for path in sorted(RETRAINING_ROOT.iterdir(), key=lambda item: item.name, reverse=True):
        if not path.is_dir() or not path.name.isdigit():
            continue
        try:
            jobs.append(load_export_summary(int(path.name)))
        except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
            jobs.append({"jobId": int(path.name), "status": "invalid", "error": "Resumen no disponible"})
    return jobs


@admin_router.get("/models/history")
async def list_model_history(
    current_user: User = Depends(require_role("supervisor", "ti", "admin")),
):
    del current_user
    history = []
    for path in sorted(model_manager.archive_dir.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        action = "rejected" if path.parent.name == "rejected" else "rollback" if payload.get("rollback_applied") else "promoted"
        history.append(
            {
                "version": payload.get("active_version") or payload.get("candidate_version"),
                "status": action,
                "admin": payload.get("admin") or payload.get("promoted_by") or payload.get("rejected_by"),
                "date": payload.get("rejected_at") or payload.get("promoted_at") or payload.get("trained_at"),
                "reason": payload.get("rejection_reason") or payload.get("promotion_reason") or payload.get("reason"),
            }
        )
    return history


@admin_router.get("/{job_id}/export-summary", response_model=RetrainingExportSummary)
async def get_retraining_export_summary(
    job_id: int,
    current_user: User = Depends(require_role("supervisor", "ti", "admin")),
):
    del current_user
    try:
        return load_export_summary(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@admin_router.get("/{job_id}/download-source")
async def download_retraining_source(
    job_id: int,
    current_user: User = Depends(require_role("supervisor", "ti", "admin")),
):
    del current_user
    try:
        path = source_file(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    media_type = "text/csv" if path.suffix == ".csv" else "application/octet-stream"
    return FileResponse(path, filename=path.name, media_type=media_type)


@admin_router.get("/{job_id}/download-report")
async def download_retraining_report(
    job_id: int,
    current_user: User = Depends(require_role("supervisor", "ti", "admin")),
):
    del current_user
    path = export_report_path(job_id)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe reporte de exportacion.")
    return FileResponse(path, filename="export_report.json", media_type="application/json")


@admin_router.post("/{job_id}/train")
async def start_candidate_training(
    job_id: int,
    current_user: User = Depends(require_role("supervisor", "ti", "admin")),
):
    del current_user
    try:
        summary = load_export_summary(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if not summary["trainingAllowed"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "El dataset no es apto para entrenamiento.", "blockingReasons": summary["blockingReasons"]},
        )
    raise HTTPException(
        status_code=status.HTTP_202_ACCEPTED,
        detail="Dataset listo. Ejecute el pipeline de preparacion, gold, split y train usando el archivo exportado; active.joblib no sera modificado.",
    )


@admin_router.get("/{job_id}/recommendation")
async def get_retraining_recommendation(
    job_id: int,
    current_user: User = Depends(require_role("supervisor", "ti", "admin")),
):
    del current_user
    try:
        load_export_summary(job_id)
        return recommendation_for_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc




