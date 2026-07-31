from pydantic import BaseModel, Field


class RoleBase(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class RoleCreate(RoleBase):
    id: int | None = None


class RoleUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class RoleOut(RoleBase):
    id: int

    class Config:
        from_attributes = True




