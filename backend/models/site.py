import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.connection import Base


def gen_uuid() -> str:
    return uuid.uuid4().hex[:12]


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    customer_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_info: Mapped[str | None] = mapped_column(Text, nullable=True)

    cpe_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    cpe_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    wan_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)

    isp_profile_id: Mapped[str | None] = mapped_column(String(12), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    devices = relationship("Device", back_populates="site", cascade="all, delete-orphan")
    jobs = relationship("ConfigJob", back_populates="site", cascade="all, delete-orphan")
