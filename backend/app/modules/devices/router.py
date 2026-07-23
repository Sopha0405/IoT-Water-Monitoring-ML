from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.core.config import settings
from app.db.postgres import get_db
from app.modules.devices.model import Device
from app.modules.devices.schemas import DeviceCreate, DeviceOut, DeviceUpdate
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
    if floor:
        query = query.filter(Device.floor == floor)
    if status_filter:
        query = query.filter(Device.status == status_filter)
    if current_user.role_id != settings.admin_role_id:
        if not current_user.floor:
            return []
        query = query.filter(Device.floor == current_user.floor)
    return query.order_by(Device.floor.asc(), Device.device_id.asc()).all()


@router.get("/{device_pk}", response_model=DeviceOut)
def get_device(
    device_pk: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Device).filter(Device.id == device_pk)
    if current_user.role_id != settings.admin_role_id:
        query = query.filter(Device.floor == current_user.floor)
    device = query.first()
    if not device:
        raise HTTPException(status_code=404, detail="Dispositivo no existe.")
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

    device = Device(**data.model_dump())
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

