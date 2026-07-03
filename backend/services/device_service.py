from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from models.device import Device, DeviceBrand, DHCPMode
from core.encryption import encrypt, decrypt


class DeviceService:

    @staticmethod
    async def create(session: AsyncSession, data: dict) -> Device:
        enc_fields = ["admin_user_encrypted", "admin_password_encrypted",
                       "wifi_ssid_encrypted", "wifi_password_encrypted"]
        for field in enc_fields:
            plain_field = field.replace("_encrypted", "")
            if plain_field in data and data[plain_field]:
                data[field] = encrypt(str(data.pop(plain_field)))

        device = Device(**data)
        session.add(device)
        await session.commit()
        await session.refresh(device)
        return device

    @staticmethod
    async def get_by_id(session: AsyncSession, device_id: str) -> Device | None:
        result = await session.execute(select(Device).where(Device.id == device_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_all(session: AsyncSession, site_id: str | None = None) -> list[Device]:
        stmt = select(Device)
        if site_id:
            stmt = stmt.where(Device.site_id == site_id)
        result = await session.execute(stmt.order_by(Device.updated_at.desc()))
        return list(result.scalars().all())

    @staticmethod
    async def update(session: AsyncSession, device_id: str, data: dict) -> Device | None:
        device = await DeviceService.get_by_id(session, device_id)
        if not device:
            return None

        enc_fields = ["admin_user_encrypted", "admin_password_encrypted",
                       "wifi_ssid_encrypted", "wifi_password_encrypted"]
        for field in enc_fields:
            plain_field = field.replace("_encrypted", "")
            if plain_field in data and data[plain_field]:
                data[field] = encrypt(str(data.pop(plain_field)))

        data["updated_at"] = datetime.utcnow()
        for key, val in data.items():
            if hasattr(device, key):
                setattr(device, key, val)

        await session.commit()
        await session.refresh(device)
        return device

    @staticmethod
    async def delete(session: AsyncSession, device_id: str) -> bool:
        result = await session.execute(delete(Device).where(Device.id == device_id))
        await session.commit()
        return result.rowcount > 0

    @staticmethod
    async def update_online_status(session: AsyncSession, device_id: str, is_online: bool) -> None:
        device = await DeviceService.get_by_id(session, device_id)
        if device:
            device.is_online = is_online
            device.last_seen = datetime.utcnow()
            await session.commit()

    @staticmethod
    def to_dict(device: Device, decrypt_secrets: bool = False) -> dict:
        d = {
            "id": device.id,
            "site_id": device.site_id,
            "name": device.name,
            "brand": device.brand.value if device.brand else "unknown",
            "model": device.model,
            "firmware_version": device.firmware_version,
            "mac_address": device.mac_address,
            "ip_address": device.ip_address,
            "subnet_mask": device.subnet_mask,
            "admin_username": decrypt(device.admin_user_encrypted) if decrypt_secrets else None,
            "admin_password": decrypt(device.admin_password_encrypted) if decrypt_secrets else None,
            "admin_web_port": device.admin_web_port,
            "wifi_ssid": decrypt(device.wifi_ssid_encrypted) if decrypt_secrets else None,
            "wifi_password": decrypt(device.wifi_password_encrypted) if decrypt_secrets else None,
            "dhcp_mode": device.dhcp_mode.value if device.dhcp_mode else "unknown",
            "bridge_mode": device.bridge_mode,
            "wifi_enabled": device.wifi_enabled,
            "custom_config": device.custom_config,
            "tags": device.tags,
            "is_online": device.is_online,
            "last_seen": device.last_seen.isoformat() if device.last_seen else None,
            "created_at": device.created_at.isoformat() if device.created_at else None,
            "updated_at": device.updated_at.isoformat() if device.updated_at else None,
        }
        return d
