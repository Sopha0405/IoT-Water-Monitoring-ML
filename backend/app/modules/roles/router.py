from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.db.postgres import get_db
from app.modules.roles.model import Role
from app.modules.roles.schemas import RoleCreate, RoleOut, RoleUpdate
from app.modules.users.model import User

router = APIRouter(prefix="/api/v1/roles", tags=["roles"])


@router.get("/", response_model=list[RoleOut])
def list_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Role).order_by(Role.id.asc()).all()


@router.post("/", response_model=RoleOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
def create_role(data: RoleCreate, db: Session = Depends(get_db)):
    exists = db.query(Role).filter(Role.name == data.name).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El rol ya existe.")

    role = Role(id=data.id, name=data.name) if data.id is not None else Role(name=data.name)
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


@router.put("/{role_id}", response_model=RoleOut, dependencies=[Depends(require_admin)])
def update_role(role_id: int, data: RoleUpdate, db: Session = Depends(get_db)):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Rol no existe.")

    exists = db.query(Role).filter(Role.name == data.name, Role.id != role_id).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El rol ya existe.")

    role.name = data.name
    db.commit()
    db.refresh(role)
    return role




