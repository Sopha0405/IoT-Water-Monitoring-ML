import base64
import random
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.security import create_access_token, verify_password
from app.db.postgres import get_db
from app.modules.auth.schemas import LoginChallengeOut, LoginIn, TokenOut, VerifyTwoFactorIn
from app.modules.users.model import User

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
OTP_TTL_SECONDS = 300
_pending_challenges: dict[str, dict] = {}


def _phone_hint(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = "".join(char for char in phone if char.isdigit())
    return f"***{digits[-4:]}" if len(digits) > 4 else phone


def _normalize_whatsapp_number(phone: str | None) -> str:
    digits = "".join(char for char in (phone or "") if char.isdigit())
    if not digits:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="El usuario no tiene telefono para WhatsApp.")
    if not digits.startswith("591") and len(digits) == 8:
        digits = f"591{digits}"
    return f"whatsapp:+{digits}"


def _send_whatsapp_code(user: User, code: str) -> None:
    if not all([settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_whatsapp_from]):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WhatsApp 2FA no esta configurado. Defina TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN y TWILIO_WHATSAPP_FROM.",
        )
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
    payload = urllib.parse.urlencode(
        {
            "From": settings.twilio_whatsapp_from,
            "To": _normalize_whatsapp_number(user.phone),
            "Body": f"Codigo de verificacion IoT Water Monitoring: {code}. Valido por 5 minutos.",
        }
    ).encode("utf-8")
    credentials = f"{settings.twilio_account_sid}:{settings.twilio_auth_token}".encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="POST")
    request.add_header("Authorization", f"Basic {base64.b64encode(credentials).decode('ascii')}")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            if response.status >= 300:
                raise RuntimeError(f"Twilio HTTP {response.status}")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="No fue posible enviar el codigo por WhatsApp.") from exc


@router.post("/login")
def login_json(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales invalidas.")
    if not verify_password(data.password, user.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales invalidas.")

    if settings.whatsapp_2fa_enabled:
        challenge_id = uuid4().hex
        code = f"{random.randint(0, 999999):06d}"
        _send_whatsapp_code(user, code)
        _pending_challenges[challenge_id] = {
            "user_id": user.id,
            "code": code,
            "expires_at": datetime.now(timezone.utc) + timedelta(seconds=OTP_TTL_SECONDS),
            "attempts": 0,
        }
        return LoginChallengeOut(
            challenge_id=challenge_id,
            phone_hint=_phone_hint(user.phone),
            expires_in_seconds=OTP_TTL_SECONDS,
        )

    token = create_access_token(subject=str(user.id))
    return {"access_token": token, "token_type": "bearer", "user": user}


@router.post("/verify-2fa", response_model=TokenOut)
def verify_two_factor(data: VerifyTwoFactorIn, db: Session = Depends(get_db)):
    challenge = _pending_challenges.get(data.challenge_id)
    if not challenge:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Codigo expirado o solicitud invalida.")
    if datetime.now(timezone.utc) > challenge["expires_at"]:
        _pending_challenges.pop(data.challenge_id, None)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Codigo expirado. Inicie sesion nuevamente.")
    challenge["attempts"] += 1
    if challenge["attempts"] > 5:
        _pending_challenges.pop(data.challenge_id, None)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Demasiados intentos. Inicie sesion nuevamente.")
    if data.code.strip() != challenge["code"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Codigo de verificacion invalido.")

    user = db.query(User).filter(User.id == challenge["user_id"]).first()
    _pending_challenges.pop(data.challenge_id, None)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuario no disponible.")
    token = create_access_token(subject=str(user.id))
    return {"access_token": token, "token_type": "bearer", "user": user}


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {"user": current_user}
