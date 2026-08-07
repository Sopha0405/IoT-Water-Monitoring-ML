from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.devices.model import Device
from app.modules.floors.model import Floor
from app.modules.floors.schemas import FloorCreate, FloorUpdate


def floor_to_dict(floor: Floor, device_count: int = 0) -> dict:
    return {
        "id": floor.id,
        "code": floor.code,
        "name": floor.name,
        "description": floor.description,
        "is_active": floor.is_active,
        "created_at": floor.created_at,
        "updated_at": floor.updated_at,
        "device_count": device_count,
    }


def list_floors(db: Session, include_inactive: bool = False) -> list[dict]:
    query = db.query(Floor)
    if not include_inactive:
        query = query.filter(Floor.is_active.is_(True))
    floors = query.order_by(Floor.code.asc()).all()
    counts = dict(
        db.query(Device.floor_id, func.count(Device.id))
        .filter(Device.floor_id.isnot(None))
        .group_by(Device.floor_id)
        .all()
    )
    return [floor_to_dict(floor, counts.get(floor.id, 0)) for floor in floors]


def get_floor_or_404(db: Session, floor_id: int) -> Floor:
    floor = db.query(Floor).filter(Floor.id == floor_id).first()
    if not floor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Piso no existe.")
    return floor


def ensure_floor_available(db: Session, floor_id: int | None) -> Floor | None:
    if floor_id is None:
        return None
    floor = get_floor_or_404(db, floor_id)
    if not floor.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El piso esta inactivo.")
    return floor


def create_floor(db: Session, data: FloorCreate) -> Floor:
    exists = db.query(Floor).filter(Floor.code == data.code).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El codigo de piso ya existe.")
    floor = Floor(**data.model_dump())
    db.add(floor)
    db.commit()
    db.refresh(floor)
    return floor


def update_floor(db: Session, floor_id: int, data: FloorUpdate) -> Floor:
    floor = get_floor_or_404(db, floor_id)
    payload = data.model_dump(exclude_unset=True)
    if "code" in payload and payload["code"] != floor.code:
        exists = db.query(Floor).filter(Floor.code == payload["code"], Floor.id != floor_id).first()
        if exists:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El codigo de piso ya existe.")
    for key, value in payload.items():
        setattr(floor, key, value)
    db.commit()
    db.refresh(floor)
    return floor


def delete_floor(db: Session, floor_id: int) -> None:
    floor = get_floor_or_404(db, floor_id)
    device_count = db.query(Device).filter(Device.floor_id == floor.id).count()
    if device_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede eliminar un piso con dispositivos asociados.",
        )
    db.delete(floor)
    db.commit()
