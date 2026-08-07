from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.access import floor_variants, resolve_floor_scope
from app.core.deps import get_current_user, require_admin
from app.core.security import hash_password
from app.db.postgres import get_db
from app.modules.floors.model import Floor
from app.modules.users.model import User
from app.modules.users.schemas import UserChangePassword, UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/api/v1/users", tags=["users"])


def resolve_user_floor_id(db: Session, floor_id: int | None, floor: str | None) -> int | None:
    if floor_id is not None:
        return floor_id
    if not floor:
        return None
    row = db.query(Floor).filter(Floor.code == floor).first()
    return row.id if row else None


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(User)
    scoped_floor = resolve_floor_scope(current_user)
    if scoped_floor:
        query = query.filter(User.floor.in_(floor_variants(scoped_floor)))
    return query.order_by(User.id.asc()).all()


@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no existe.")

    scoped_floor = resolve_floor_scope(current_user)
    if scoped_floor and user.floor not in floor_variants(scoped_floor):
        raise HTTPException(status_code=404, detail="Usuario no existe.")
    return user


@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
def create_user(data: UserCreate, db: Session = Depends(get_db)):
    exists = db.query(User).filter(User.email == data.email).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El email ya existe.")

    user = User(
        name=data.name,
        email=data.email,
        password=hash_password(data.password),
        phone=data.phone,
        floor_id=resolve_user_floor_id(db, data.floor_id, data.floor),
        floor=data.floor,
        limit_to_floor=data.limit_to_floor,
        role_id=data.role_id,
        is_active=data.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserOut, dependencies=[Depends(require_admin)])
def update_user(user_id: int, data: UserUpdate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no existe.")

    payload = data.model_dump(exclude_unset=True)
    if "email" in payload and payload["email"] != user.email:
        exists = db.query(User).filter(User.email == payload["email"]).first()
        if exists:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El email ya existe.")

    for key, value in payload.items():
        if key == "floor" and "floor_id" not in payload:
            user.floor_id = resolve_user_floor_id(db, None, value)
        setattr(user, key, value)

    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}/password", dependencies=[Depends(require_admin)])
def change_password(user_id: int, data: UserChangePassword, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no existe.")

    user.password = hash_password(data.password)
    db.commit()
    return {"updated": True}


@router.delete("/{user_id}", dependencies=[Depends(require_admin)])
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no existe.")
    db.delete(user)
    db.commit()
    return {"deleted": True}




