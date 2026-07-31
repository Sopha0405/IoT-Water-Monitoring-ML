from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, require_admin
from app.db.postgres import get_db
from app.modules.alerts.model import Alert
from app.modules.alerts.schemas import AlertCreate, AlertOut, AlertUpdate
from app.modules.ml_analysis.inference.model import MLAnalysis
from app.modules.users.model import User

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


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
    if floor:
        query = query.filter(Alert.floor == floor)
    if current_user.role_id != settings.admin_role_id:
        query = query.filter(Alert.floor == current_user.floor)
    alerts = query.order_by(Alert.detected_at.desc()).all()
    rows = []
    for alert in alerts:
        analysis = (
            db.query(MLAnalysis)
            .filter(MLAnalysis.alert_id == alert.id)
            .order_by(MLAnalysis.processed_at.desc())
            .first()
        )
        rows.append(
            {
                "id": alert.id,
                "device_id": alert.device_id,
                "floor": alert.floor,
                "anomaly_type": alert.anomaly_type,
                "severity": alert.severity,
                "risk_percentage": alert.risk_percentage,
                "status": alert.status,
                "description": alert.description,
                "detected_at": alert.detected_at,
                "attended_by": alert.attended_by,
                "attended_at": alert.attended_at,
                "observed_value": analysis.observed_value if analysis else None,
                "last_detected_at": analysis.processed_at if analysis else alert.detected_at,
            }
        )
    return rows


@router.post("/", response_model=AlertOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
def create_alert(data: AlertCreate, db: Session = Depends(get_db)):
    alert = Alert(**data.model_dump(exclude_none=True))
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


@router.put("/{alert_id}", response_model=AlertOut, dependencies=[Depends(require_admin)])
def update_alert(alert_id: int, data: AlertUpdate, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta no existe.")

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(alert, key, value)

    db.commit()
    db.refresh(alert)
    return alert


@router.patch("/{alert_id}/attend", response_model=AlertOut)
def attend_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerta no existe.")
    if current_user.role_id != settings.admin_role_id and alert.floor != current_user.floor:
        raise HTTPException(status_code=403, detail="No puedes atender esta alerta.")

    alert.status = "attended"
    alert.attended_by = current_user.id
    alert.attended_at = datetime.utcnow()
    db.commit()
    db.refresh(alert)
    return alert




