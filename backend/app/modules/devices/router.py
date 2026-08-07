from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.access import ensure_floor_access, floor_variants, normalize_floor_code, resolve_floor_scope
from app.core.deps import get_current_user, require_admin
from app.core.config import settings
from app.db.postgres import get_db
from app.modules.alerts.model import Alert
from app.modules.devices.model import Device
from app.modules.devices.schemas import DeviceCreate, DeviceOut, DeviceUpdate
from app.modules.floors.service import ensure_floor_available
from app.modules.telemetry.service import get_latest_telemetry
from app.modules.users.model import User

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


@router.get("/", response_model=list[DeviceOut])
def list_devices(
    floor: str | None = None,
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Device)
    scoped_floor = resolve_floor_scope(current_user, floor)
    if scoped_floor:
        query = query.filter(Device.floor.in_(floor_variants(scoped_floor)))
    if status_filter:
        query = query.filter(Device.status == status_filter)
    return query.order_by(Device.floor.asc(), Device.device_id.asc()).all()


@router.get("/iot/config")
def iot_config(current_user: User = Depends(get_current_user)):
    del current_user
    return {
        "site": settings.site,
        "topic_template": settings.mqtt_topic_template,
        "sample_seconds": 5,
        "required_payload_fields": [
            "schema_version",
            "site",
            "device_id",
            "floor",
            "flow_lpm",
            "sample_seconds",
            "status",
            "simulated",
            "ts",
        ],
    }


@router.get("/active-telemetry")
def active_telemetry_devices(
    floor: str | None = None,
    limit: int = 300,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scoped_floor = resolve_floor_scope(current_user, floor)
    devices = {device.device_id: device for device in db.query(Device).all()}
    alert_counts = dict(
        db.query(Alert.device_id, func.count(Alert.id))
        .group_by(Alert.device_id)
        .all()
    )
    active_alert_counts = dict(
        db.query(Alert.device_id, func.count(Alert.id))
        .filter(Alert.status.in_(["pendiente", "open", "acknowledged", "reviewing", "investigating", "confirmed_leak"]))
        .group_by(Alert.device_id)
        .all()
    )
    points = get_latest_telemetry(floor=scoped_floor, field="flow_lpm", limit=limit)
    latest_by_device = {}
    for point in sorted(points, key=lambda item: item.time, reverse=True):
        if point.source != "real" or not point.device_id or point.device_id in latest_by_device:
            continue
        latest_by_device[point.device_id] = point

    rows = []
    for device_id, point in latest_by_device.items():
        device = devices.get(device_id)
        if not device:
            continue
        floor_info = device.floor_info if device else None
        row_floor = point.floor or (floor_info.code if floor_info else device.floor if device else None)
        if scoped_floor and normalize_floor_code(row_floor) != scoped_floor:
            continue
        rows.append(
            {
                "id": device.id if device else None,
                "device_id": device_id,
                "floor_id": device.floor_id if device else None,
                "floor": row_floor,
                "floor_info": (
                    {"id": floor_info.id, "code": floor_info.code, "name": floor_info.name}
                    if floor_info
                    else None
                ),
                "location": device.location if device and device.location else None,
                "sensor_type": device.sensor_type if device else None,
                "status": "active",
                "registered": bool(device),
                "reading": point.value,
                "last_seen": point.time,
                "source": point.source,
                "alert_count": int(alert_counts.get(device.id if device else None, 0)),
                "active_alert_count": int(active_alert_counts.get(device.id if device else None, 0)),
                "site": point.site,
                "tenant": point.tenant,
                "mqtt_topic": settings.mqtt_topic_template.format(site=settings.site, device_id=device_id),
            }
        )
    for device in devices.values():
        if device.device_id in latest_by_device:
            continue
        if scoped_floor and normalize_floor_code(device.floor) != scoped_floor:
            continue
        floor_info = device.floor_info
        rows.append(
            {
                "id": device.id,
                "device_id": device.device_id,
                "floor_id": device.floor_id,
                "floor": device.floor,
                "floor_info": (
                    {"id": floor_info.id, "code": floor_info.code, "name": floor_info.name}
                    if floor_info
                    else None
                ),
                "location": device.location,
                "sensor_type": device.sensor_type,
                "status": device.status,
                "registered": True,
                "reading": None,
                "last_seen": None,
                "source": "inventory",
                "alert_count": int(alert_counts.get(device.id, 0)),
                "active_alert_count": int(active_alert_counts.get(device.id, 0)),
                "site": settings.site,
                "tenant": None,
                "mqtt_topic": settings.mqtt_topic_template.format(site=settings.site, device_id=device.device_id),
            }
        )
    return sorted(rows, key=lambda item: (str(item["floor"] or ""), item["device_id"]))


@router.get("/{device_pk}", response_model=DeviceOut)
def get_device(
    device_pk: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Device).filter(Device.id == device_pk)
    device = query.first()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no existe.")
    ensure_floor_access(current_user, device.floor)
    return device


@router.post("/", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
def create_device(
    data: DeviceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    exists = db.query(Device).filter(Device.device_id == data.device_id).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El device_id ya existe.")

    payload = data.model_dump()
    floor = ensure_floor_available(db, payload.get("floor_id"))
    if floor and not payload.get("floor"):
        payload["floor"] = floor.code

    device = Device(**payload)
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


@router.put("/{device_pk}", response_model=DeviceOut)
def update_device(
    device_pk: int,
    data: DeviceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    device = db.query(Device).filter(Device.id == device_pk).first()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no existe.")

    payload = data.model_dump(exclude_unset=True)
    if "device_id" in payload and payload["device_id"] != device.device_id:
        exists = db.query(Device).filter(Device.device_id == payload["device_id"]).first()
        if exists:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El device_id ya existe.")
    if "floor_id" in payload:
        floor = ensure_floor_available(db, payload["floor_id"])
        if floor and "floor" not in payload:
            payload["floor"] = floor.code

    for key, value in payload.items():
        setattr(device, key, value)

    db.commit()
    db.refresh(device)
    return device


@router.delete("/{device_pk}")
def delete_device(
    device_pk: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    device = db.query(Device).filter(Device.id == device_pk).first()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no existe.")

    db.delete(device)
    db.commit()
    return {"deleted": True}





