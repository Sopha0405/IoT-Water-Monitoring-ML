from sqlalchemy import String, Text, Boolean, BigInteger, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True, nullable=False)

    first_name: Mapped[str] = mapped_column(String(80), nullable=False)
    last_paternal: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_maternal: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cod_employee: Mapped[str | None] = mapped_column(String(40), nullable=True)
    password: Mapped[str] = mapped_column(Text, nullable=False)

    role_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tenant_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[object] = mapped_column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    ci: Mapped[int | None] = mapped_column(Integer, nullable=True)
    telefono: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
