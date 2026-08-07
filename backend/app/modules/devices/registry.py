from sqlalchemy.orm import Session

from app.core.access import normalize_floor_code
from app.modules.devices.model import Device
from app.modules.floors.model import Floor


def ensure_device_registered(
    db: Session,
    device_id: str | None,
    floor: str | None = None,
    sensor_type: str = "FS300A",
) -> Device | None:
    if not device_id:
        return None

    device = db.query(Device).filter(Device.device_id == device_id).first()
    if device:
        if floor and not device.floor:
            device.floor = normalize_floor_code(floor)
        return device

    floor_code = normalize_floor_code(floor)
    floor_row = db.query(Floor).filter(Floor.code == floor_code).first() if floor_code else None
    device = Device(
        device_id=device_id,
        floor_id=floor_row.id if floor_row else None,
        floor=floor_code,
        location="Registrado automaticamente por telemetria",
        sensor_type=sensor_type,
        status="active",
    )
    db.add(device)
    db.flush()
    return device
