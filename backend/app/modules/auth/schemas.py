from pydantic import BaseModel, EmailStr


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class LoginChallengeOut(BaseModel):
    requires_2fa: bool = True
    challenge_id: str
    channel: str = "whatsapp"
    phone_hint: str | None = None
    expires_in_seconds: int


class VerifyTwoFactorIn(BaseModel):
    challenge_id: str
    code: str


class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    phone: str | None = None
    floor: str | None = None
    role_id: int
    is_active: bool

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
