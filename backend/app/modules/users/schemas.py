from pydantic import BaseModel, EmailStr, Field


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


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8)
    phone: str | None = None
    floor: str | None = None
    role_id: int
    is_active: bool = True


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    email: EmailStr | None = None
    phone: str | None = None
    floor: str | None = None
    role_id: int | None = None
    is_active: bool | None = None


class UserChangePassword(BaseModel):
    password: str = Field(min_length=8)




