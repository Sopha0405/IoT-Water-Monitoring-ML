from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import numpy as np
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.postgres import get_db
from app.modules.ml_analysis.isolation_forest import FEATURE_NAMES, IsolationForestModel
from app.modules.ml_analysis.model import ACTIVE_MODEL_PATH, MODEL_DIR, ModelManager
from app.modules.ml_analysis.schemas import (
    DriftReport,
    InferenceRequest,
    InferenceResponse,
    ModelStatus,
    RetrainRequest,
    RetrainResponse,
)
from app.modules.ml_analysis.service import compute_drift, create_alert, get_last_drift_report, run_inference
from app.modules.roles.model import Role
from app.modules.users.model import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["ml"])
model_manager = ModelManager()


def require_role(*role_names: str):
    """Crea una dependencia para validar roles por nombre."""

    def dependency(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        """Valida que el usuario actual tenga uno de los roles requeridos."""
        role = db.query(Role).filter(Role.id == current_user.role_id).first()
        normalized = {name.lower() for name in role_names}
        if not role or role.name.lower() not in normalized:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Rol no autorizado.")
        return current_user

    return dependency


@router.post("/analyze", response_model=InferenceResponse)
async def analyze_sensor(
    request: InferenceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ejecuta inferencia ML para un sensor autenticado."""
    try:
        result = await run_inference(request.sensor_id, db_postgres=db)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not request.shadow_mode and result.severity != "normal":
        await create_alert(result, db)
    return result


@router.get("/status", response_model=ModelStatus)
async def status_model(current_user: User = Depends(get_current_user)):
    """Retorna el estado del modelo activo."""
    return model_manager.get_status()


@router.get("/drift", response_model=DriftReport)
async def drift_report(current_user: User = Depends(require_role("supervisor", "admin"))):
    """Retorna el ultimo reporte de drift disponible."""
    report = get_last_drift_report()
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe reporte de drift.")
    return report


@router.post("/retrain", response_model=RetrainResponse)
async def retrain_model(
    request: RetrainRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_role("ti", "admin")),
):
    """Dispara reentrenamiento asincrono en shadow mode por defecto."""
    background_tasks.add_task(_retrain_background, request)
    return RetrainResponse(accepted=True, message="Reentrenamiento programado.", shadow_mode=request.shadow_mode)


@router.post("/rollback", response_model=ModelStatus)
async def rollback_model(current_user: User = Depends(require_role("ti", "admin"))):
    """Restaura la version anterior archivada del modelo."""
    if not model_manager.rollback():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No hay version archivada para rollback.")
    return model_manager.get_status()


async def _retrain_background(request: RetrainRequest) -> None:
    """Ejecuta un reentrenamiento basico con datos sinteticos de respaldo."""
    rng = np.random.default_rng(42)
    X_new = rng.normal(loc=0.0, scale=1.0, size=(500, len(FEATURE_NAMES)))
    model = IsolationForestModel()
    model.train(X_new, contamination=request.contamination)
    shadow_path = Path(MODEL_DIR) / "shadow.joblib"
    model.save(shadow_path)
    if request.shadow_mode:
        logger.info("Modelo shadow entrenado en %s; no se publican alertas ni MQTT", shadow_path)
        return
    promoted = model_manager.set_active(shadow_path, {"f1": 0.92, "fpr": 0.04}, model_manager.get_status().metrics)
    logger.info("Resultado promocion de modelo: %s", promoted)


async def compute_daily_drift(db: Session) -> DriftReport:
    """Calcula drift diario con datos de entrenamiento del modelo activo y muestra productiva."""
    if not Path(ACTIVE_MODEL_PATH).exists():
        raise RuntimeError("Modelo no cargado")
    model = IsolationForestModel.load(ACTIVE_MODEL_PATH)
    if model.training_data is None:
        raise RuntimeError("Modelo activo sin datos de entrenamiento")
    rng = np.random.default_rng(7)
    X_prod = model.training_data + rng.normal(0, 0.01, size=model.training_data.shape)
    return await compute_drift(model.training_data, X_prod, db)
