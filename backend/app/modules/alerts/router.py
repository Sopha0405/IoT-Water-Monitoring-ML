from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.access import ensure_floor_access, floor_variants, resolve_floor_scope
from app.core.deps import get_current_user, require_admin
from app.db.postgres import get_db
from app.modules.alerts.model import Alert
from app.modules.alerts.schemas import AlertCreate, AlertOut, AlertUpdate
from app.modules.devices.model import Device
from app.modules.devices.registry import ensure_device_registered
from app.modules.ml_analysis.inference.model import MLAnalysis
from app.modules.users.model import User

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


class AlertStatusUpdate(BaseModel):
    status: str
    observations: str | None = None


def alert_to_dict(alert: Alert, db: Session) -> dict:
    analysis = (
        db.query(MLAnalysis)
        .filter(MLAnalysis.alert_id == alert.id)
        .order_by(MLAnalysis.processed_at.desc())
        .first()
    )
    device = alert.device
    floor = device.floor if device else None
    return {
        "id": alert.id,
        "device_id": device.device_id if device else str(alert.device_id),
        "floor": floor,
        "anomaly_type": alert.anomaly_type,
        "severity": alert.severity,
        "risk_percentage": alert.risk_percentage or 0,
        "status": alert.status,
        "description": alert.description,
        "detected_at": alert.detected_at,
        "attended_by": alert.attended_by,
        "attended_at": alert.attended_at,
        "observed_value": analysis.observed_value if analysis else None,
        "last_detected_at": analysis.processed_at if analysis else alert.detected_at,
    }


@router.get("/", response_model=list[AlertOut])
def list_alerts(
    status_filter: str | None = Query(default=None, alias="status"),
    floor: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Alert)
    if status_filter:
        query = query.filter(Alert.status == status_filter)
    scoped_floor = resolve_floor_scope(current_user, floor)
    if scoped_floor:
        query = query.join(Device).filter(Device.floor.in_(floor_variants(scoped_floor)))
    alerts = query.order_by(Alert.detected_at.desc()).all()
    return [alert_to_dict(alert, db) for alert in alerts]


@router.post("/", response_model=AlertOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
def create_alert(data: AlertCreate, db: Session = Depends(get_db)):
    payload = data.model_dump(exclude_none=True)
    device = ensure_device_registered(db, str(payload.pop("device_id")), payload.pop("floor", None))
    alert = Alert(device_id=device.id, **payload)
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert_to_dict(alert, db)


@router.put("/{alert_id}", response_model=AlertOut, dependencies=[Depends(require_admin)])
def update_alert(alert_id: int, data: AlertUpdate, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta no existe.")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(alert, key, value)

    db.commit()
    db.refresh(alert)
    return alert_to_dict(alert, db)


@router.patch("/{alert_id}/status", response_model=AlertOut)
def update_alert_status(
    alert_id: int,
    data: AlertStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta no existe.")
    ensure_floor_access(current_user, alert.device.floor if alert.device else None)

    alert.status = data.status
    if data.observations:
        alert.description = data.observations[:500]
    if data.status in {"attended", "resolved", "closed", "false_positive", "confirmed_leak"}:
        alert.attended_by = current_user.id
        alert.attended_at = datetime.utcnow()

    db.commit()
    db.refresh(alert)
    return alert_to_dict(alert, db)


@router.patch("/{alert_id}/attend", response_model=AlertOut)
def attend_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta no existe.")
    ensure_floor_access(current_user, alert.device.floor if alert.device else None)

    alert.status = "attended"
    alert.attended_by = current_user.id
    alert.attended_at = datetime.utcnow()
    db.commit()
    db.refresh(alert)
    return alert_to_dict(alert, db)




