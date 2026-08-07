from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True, nullable=False)
    password: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    floor_id: Mapped[int | None] = mapped_column(ForeignKey("floors.id"), index=True, nullable=True)
    floor: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    limit_to_floor: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    role = relationship("Role", back_populates="users")
    floor_ref = relationship("Floor", back_populates="users")
    attended_alerts = relationship("Alert", back_populates="attended_by_user")
    feedback_entries = relationship(
        "MLAlertFeedback",
        back_populates="operator",
    )




