import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.connection import Base


def gen_uuid() -> str:
    return uuid.uuid4().hex[:12]


class Baseline(Base):
    __tablename__ = "baselines"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_uuid)
    device_id: Mapped[str] = mapped_column(String(12), ForeignKey("devices.id"), nullable=False)
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)

    full_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    running_state: Mapped[dict] = mapped_column(JSON, nullable=False)

    triggered_by: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    device = relationship("Device", back_populates="baselines")
