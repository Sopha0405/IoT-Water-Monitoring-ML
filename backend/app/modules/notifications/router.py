import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.access import floor_variants, resolve_floor_scope
from app.db.postgres import get_db
from app.core.deps import get_current_user
from app.modules.alerts.model import Alert
from app.modules.devices.model import Device
from app.modules.telemetry.service import get_latest_telemetry
from app.modules.users.model import User

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])

STATE_PATH = Path("data/notifications/read_state.json")
def _read_state() -> dict[str, list[str]]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_state(state: dict[str, list[str]]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _mark_read(user_id: int, notification_ids: list[str]) -> None:
    state = _read_state()
    key = str(user_id)
    state[key] = sorted(set(state.get(key, [])) | set(notification_ids))
    _write_state(state)


def _severity_for_alert(alert: Alert) -> str:
    risk = float(alert.risk_percentage or 0)
    if alert.severity:
        return alert.severity
    if risk >= 80:
        return "critical"
    if risk >= 60:
        return "warning"
    return "info"


def _alert_title(alert: Alert) -> str:
    floor = alert.device.floor if alert.device else "sin piso"
    if alert.status in {"resolved", "closed", "attended"}:
        return f"Alerta resuelta en {floor}"
    if alert.status == "confirmed_leak":
        return f"Alerta confirmada en {floor}"
    return f"Nueva alerta en {floor}"


def _base_alert_query(db: Session, current_user: User):
    query = db.query(Alert)
    scoped_floor = resolve_floor_scope(current_user)
    if scoped_floor:
        query = query.join(Device).filter(Device.floor.in_(floor_variants(scoped_floor)))
    return query


def _generate_notifications(db: Session, current_user: User) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    alerts = _base_alert_query(db, current_user).order_by(Alert.detected_at.desc()).limit(40).all()
    for alert in alerts:
        rows.append(
            {
                "id": f"alert-{alert.id}-{alert.status}",
                "type": "alert",
                "severity": _severity_for_alert(alert),
                "title": _alert_title(alert),
                "message": (alert.description or alert.anomaly_type or "Alerta operativa detectada")[:160],
                "created_at": alert.detected_at,
                "floor": alert.device.floor if alert.device else None,
                "device_id": alert.device.device_id if alert.device else str(alert.device_id),
                "status": alert.status,
            }
        )

    device_query = db.query(Device)
    scoped_floor = resolve_floor_scope(current_user)
    if scoped_floor:
        device_query = device_query.filter(Device.floor.in_(floor_variants(scoped_floor)))
    devices = device_query.all()
    visible_floor = resolve_floor_scope(current_user)
    latest_points = get_latest_telemetry(floor=visible_floor, field="flow_lpm", limit=300)
    live_device_ids = {point.device_id for point in latest_points if point.source == "real" and point.device_id}
    now = datetime.utcnow()

    for device in devices:
        if device.status and device.status != "active":
            rows.append(
                {
                    "id": f"device-{device.id}-{device.status}",
                    "type": "device",
                    "severity": "critical" if device.status == "offline" else "warning",
                    "title": f"Dispositivo {device.device_id} {device.status}",
                    "message": "Revisar estado operativo del sensor.",
                    "created_at": now,
                    "floor": device.floor,
                    "device_id": device.device_id,
                    "status": device.status,
                }
            )
        if device.device_id not in live_device_ids:
            rows.append(
                {
                    "id": f"device-{device.id}-sin-telemetria",
                    "type": "device",
                    "severity": "warning",
                    "title": f"Dispositivo {device.device_id} sin telemetría reciente",
                    "message": "No se recibió caudal real en la última consulta.",
                    "created_at": now,
                    "floor": device.floor,
                    "device_id": device.device_id,
                    "status": "stale",
                }
            )

    return sorted(rows, key=_sort_key, reverse=True)


def _with_read_flag(items: list[dict[str, Any]], user_id: int) -> list[dict[str, Any]]:
    read_ids = set(_read_state().get(str(user_id), []))
    return [{**item, "read": item["id"] in read_ids} for item in items]


def _sort_key(item: dict[str, Any]) -> float:
    value = item.get("created_at")
    if isinstance(value, datetime):
        return value.timestamp()
    return 0.0


@router.get("/")
def list_notifications(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notifications = _with_read_flag(_generate_notifications(db, current_user), current_user.id)
    return notifications[: max(1, min(limit, 100))]


@router.get("/unread-count")
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notifications = _with_read_flag(_generate_notifications(db, current_user), current_user.id)
    return {"count": sum(1 for item in notifications if not item["read"])}


@router.patch("/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(get_current_user),
):
    _mark_read(current_user.id, [notification_id])
    return {"read": True}


@router.patch("/read-all")
def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification_ids = [item["id"] for item in _generate_notifications(db, current_user)]
    _mark_read(current_user.id, notification_ids)
    return {"read": True, "count": len(notification_ids)}
