import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, Boolean, JSON, Integer, Float, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.connection import Base

import enum


def gen_uuid() -> str:
    return uuid.uuid4().hex[:12]


class DeviceBrand(str, enum.Enum):
    MIKROTIK = "mikrotik"
    TPLINK = "tplink"
    UBIQUITI = "ubiquiti"
    UNKNOWN = "unknown"
    GENERIC = "generic"


class DHCPMode(str, enum.Enum):
    DISABLED = "disabled"
    ENABLED = "enabled"
    RELAY = "relay"
    UNKNOWN = "unknown"


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(12), primary_key=True, default=gen_uuid)
    site_id: Mapped[str | None] = mapped_column(String(12), ForeignKey("sites.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    brand: Mapped[DeviceBrand] = mapped_column(SAEnum(DeviceBrand), default=DeviceBrand.UNKNOWN)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mac_address: Mapped[str | None] = mapped_column(String(17), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    subnet_mask: Mapped[str | None] = mapped_column(String(45), nullable=True)

    admin_user_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_web_port: Mapped[int] = mapped_column(Integer, default=80)

    wifi_ssid_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    wifi_password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    dhcp_mode: Mapped[DHCPMode] = mapped_column(SAEnum(DHCPMode), default=DHCPMode.UNKNOWN)
    bridge_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    wifi_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    custom_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tags: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    is_online: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    site = relationship("Site", back_populates="devices")
    baselines = relationship("Baseline", back_populates="device", cascade="all, delete-orphan")
    connection_profiles = relationship("ConnectionProfile", back_populates="device", cascade="all, delete-orphan")
