from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from core.drivers.base import RouterConnection
from core.drivers.factory import DriverFactory
from models.device import Device
from models.connection_profile import ConnectionProfile
from models.baseline import Baseline
from services.device_service import DeviceService
from core.encryption import encrypt, decrypt


class RemoteService:

    @staticmethod
    async def get_connection_profile(device: Device) -> dict:
        connection = {
            "host": device.ip_address,
            "ssh_port": 22,
            "username": decrypt(device.admin_user_encrypted) if device.admin_user_encrypted else "admin",
            "password": decrypt(device.admin_password_encrypted) if device.admin_password_encrypted else "",
            "web_port": device.admin_web_port,
            "brand": device.brand.value if device.brand else "generic",
        }
        return connection

    @staticmethod
    async def save_connection_profile(
        session: AsyncSession,
        device_id: str,
        profile_data: dict,
    ) -> ConnectionProfile:
        enc_fields = {
            "ssh_user": "ssh_user_encrypted",
            "ssh_password": "ssh_password_encrypted",
            "jump_user": "jump_user_encrypted",
            "jump_password": "jump_password_encrypted",
        }
        for plain, enc in enc_fields.items():
            if plain in profile_data and profile_data[plain]:
                profile_data[enc] = encrypt(str(profile_data.pop(plain)))

        profile_data["device_id"] = device_id
        profile = ConnectionProfile(**profile_data)
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile

    @staticmethod
    async def test_connection(connection_data: dict) -> dict:
        conn = RouterConnection(
            host=connection_data["host"],
            port=connection_data.get("ssh_port", 22),
            username=connection_data.get("username", "admin"),
            password=connection_data.get("password", ""),
        )
        driver = DriverFactory.create(connection_data.get("brand", "generic"), conn)

        reachable = await driver.is_reachable()
        if not reachable:
            return {"success": False, "reachable": False, "auth": False}

        connected = await driver.connect()
        if connected:
            info = await driver.get_info()
            await driver.disconnect()
            return {
                "success": True,
                "reachable": True,
                "auth": True,
                "brand": info.brand,
                "model": info.model,
                "firmware": info.firmware_version,
            }

        return {"success": False, "reachable": True, "auth": False}
