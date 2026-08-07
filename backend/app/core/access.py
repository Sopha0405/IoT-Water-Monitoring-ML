from app.core.config import settings
from app.modules.users.model import User


FLOOR_ALIASES = {
    "1": "P1",
    "piso 1": "P1",
    "p1": "P1",
    "2": "P2",
    "piso 2": "P2",
    "p2": "P2",
    "3": "P3",
    "piso 3": "P3",
    "p3": "P3",
    "pb": "PB",
    "planta baja": "PB",
}

FLOOR_LABELS = {
    "PB": "PB",
    "P1": "Piso 1",
    "P2": "Piso 2",
    "P3": "Piso 3",
}


def is_admin(user: User) -> bool:
    return user.role_id in {1, settings.admin_role_id}


def has_admin_access(user: User) -> bool:
    return is_admin(user)


def normalize_floor_code(value: str | None) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    return FLOOR_ALIASES.get(raw.lower(), raw)


def floor_variants(value: str | None) -> list[str]:
    code = normalize_floor_code(value)
    if not code:
        return []
    variants = {code, FLOOR_LABELS.get(code, code)}
    return [item for item in variants if item]


def user_floor_scope(user: User) -> list[str]:
    if not getattr(user, "limit_to_floor", False):
        return []
    floor = normalize_floor_code(user.floor)
    return [floor] if floor else []


def resolve_floor_scope(user: User, requested_floor: str | None = None) -> str | None:
    requested = normalize_floor_code(requested_floor)
    allowed = user_floor_scope(user)
    if not allowed:
        return requested
    if requested and requested not in allowed:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes acceso a este piso.")
    return allowed[0]


def ensure_floor_access(user: User, floor: str | None) -> None:
    allowed = user_floor_scope(user)
    if not allowed:
        return
    if normalize_floor_code(floor) not in allowed:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes acceso a este recurso.")
