from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.access import has_admin_access
from app.core.config import settings
from app.db.postgres import get_db
from app.modules.users.model import User

bearer_scheme = HTTPBearer(auto_error=True)


def get_current_user(
    cred: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    token = cred.credentials

    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido (sin sub).")
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido o expirado.")

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no existe.")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Usuario inactivo.")

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not has_admin_access(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo supervisor/admin.")
    return current_user


def require_supervisor(current_user: User = Depends(get_current_user)) -> User:
    if not has_admin_access(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo supervisor.")
    return current_user
