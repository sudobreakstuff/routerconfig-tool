import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, Integer, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.connection import Base


def gen_uuid() -> str:
    return uuid.uuid4().hex[:12]


class ConnectionProfile(Base):
    __tablename__ = "connection_profiles"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_uuid)
    device_id: Mapped[str] = mapped_column(String(12), ForeignKey("devices.id"), nullable=False)
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)

    ssh_host: Mapped[str] = mapped_column(String(128), nullable=False)
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    ssh_user_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    ssh_password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    ssh_key_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    ssh_command_template: Mapped[str | None] = mapped_column(Text, nullable=True)

    web_admin_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    web_admin_port: Mapped[int] = mapped_column(Integer, default=80)

    jump_host: Mapped[str | None] = mapped_column(String(128), nullable=True)
    jump_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    jump_user_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    jump_password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    last_success: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    device = relationship("Device", back_populates="connection_profiles")
