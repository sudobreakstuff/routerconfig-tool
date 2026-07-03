import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, JSON, Integer, Boolean, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.connection import Base

import enum


def gen_uuid() -> str:
    return uuid.uuid4().hex[:12]


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ConfigJob(Base):
    __tablename__ = "config_jobs"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_uuid)
    site_id: Mapped[str | None] = mapped_column(String(12), ForeignKey("sites.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[JobStatus] = mapped_column(SAEnum(JobStatus), default=JobStatus.QUEUED)
    template_id: Mapped[str | None] = mapped_column(String(12), nullable=True)

    total_devices: Mapped[int] = mapped_column(Integer, default=0)
    completed_devices: Mapped[int] = mapped_column(Integer, default=0)
    failed_devices: Mapped[int] = mapped_column(Integer, default=0)

    log: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    site = relationship("Site", back_populates="jobs")
    items = relationship("ConfigJobItem", back_populates="job", cascade="all, delete-orphan")


class ConfigJobItem(Base):
    __tablename__ = "config_job_items"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_uuid)
    job_id: Mapped[str] = mapped_column(String(12), ForeignKey("config_jobs.id"), nullable=False)
    device_id: Mapped[str] = mapped_column(String(12), nullable=False)
    device_ip: Mapped[str] = mapped_column(String(45), nullable=False)
    status: Mapped[JobStatus] = mapped_column(SAEnum(JobStatus), default=JobStatus.QUEUED)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    result_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    job = relationship("ConfigJob", back_populates="items")
