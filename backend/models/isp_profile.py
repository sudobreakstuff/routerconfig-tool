import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, JSON, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from database.connection import Base


def gen_uuid() -> str:
    return uuid.uuid4().hex[:12]


class ISPProfile(Base):
    __tablename__ = "isp_profiles"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    adapter_name: Mapped[str] = mapped_column(String(64), nullable=False)

    dhcp_server_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    dns_servers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    ntp_servers: Mapped[list | None] = mapped_column(JSON, nullable=True)

    wan_vlan: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wan_pppoe: Mapped[bool] = mapped_column(Boolean, default=False)
    wan_pppoe_username_format: Mapped[str | None] = mapped_column(String(64), nullable=True)

    custom_settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    upload_endpoint: Mapped[str | None] = mapped_column(Text, nullable=True)
    upload_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
