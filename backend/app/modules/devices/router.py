from fastapi import APIRouter, Depends
from app.core.deps import get_current_user, require_admin
from app.modules.users.model import User

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])

@router.get("/")
def list_devices(current_user: User = Depends(get_current_user)):
    return {"ok": True, "user_id": current_user.id}

@router.post("/admin-only")
def admin_action(current_user: User = Depends(require_admin)):
    return {"ok": True, "admin_id": current_user.id}

