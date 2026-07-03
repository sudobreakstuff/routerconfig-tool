import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, JSON, Boolean, Integer, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from database.connection import Base

import enum


def gen_uuid() -> str:
    return uuid.uuid4().hex[:12]


class TemplateVendor(str, enum.Enum):
    MIKROTIK = "mikrotik"
    TPLINK = "tplink"
    UBIQUITI = "ubiquiti"
    GENERIC = "generic"
    ANY = "any"


class ConfigTemplate(Base):
    __tablename__ = "config_templates"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    vendor: Mapped[TemplateVendor] = mapped_column(SAEnum(TemplateVendor), default=TemplateVendor.ANY)

    config_commands: Mapped[list | None] = mapped_column(JSON, nullable=True)
    jinja2_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    variables_schema: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
