import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, JSON, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from database.connection import Base


def gen_uuid() -> str:
    return uuid.uuid4().hex[:12]


class DiagnosticReport(Base):
    __tablename__ = "diagnostic_reports"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_uuid)
    device_id: Mapped[str] = mapped_column(String(12), nullable=False)
    baseline_id: Mapped[str | None] = mapped_column(String(12), nullable=True)

    current_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    current_state: Mapped[dict] = mapped_column(JSON, nullable=False)

    differences: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    health_checks: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    issues_found: Mapped[int] = mapped_column(default=0)
    warnings_found: Mapped[int] = mapped_column(default=0)

    is_healthy: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
