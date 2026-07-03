from __future__ import annotations

from datetime import datetime
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from core.drivers.base import RouterConnection, WiFiConfig, AdminConfig, DHCPConfig
from core.drivers.factory import DriverFactory
from models.device import Device
from models.baseline import Baseline
from core.engine import ConfigEngine, ConfigTask, ConfigTaskResult
from services.device_service import DeviceService
from core.encryption import encrypt


class ConfigService:

    @staticmethod
    async def setup_device(
        session: AsyncSession,
        device_data: dict,
        on_progress: Callable[[str], None] = None,
    ) -> ConfigTaskResult:
        task = ConfigTask(
            device_ip=device_data.get("ip_address", ""),
            device_id=device_data.get("id"),
            brand=device_data.get("brand", "unknown"),
            username=device_data.get("admin_username", device_data.get("username", "admin")),
            password=device_data.get("current_password", "admin"),
            ssh_port=device_data.get("ssh_port", 22),
            web_port=device_data.get("web_port", 80),
            wifi_ssid=device_data.get("wifi_ssid", ""),
            wifi_password=device_data.get("wifi_password", ""),
            admin_password=device_data.get("admin_password", device_data.get("new_admin_password", "")),
            admin_username=device_data.get("admin_username", "admin"),
            disable_dhcp=device_data.get("disable_dhcp", True),
            enable_bridge=device_data.get("enable_bridge", True),
            commands=device_data.get("commands", []),
            template_variables=device_data.get("template_variables", {}),
        )

        if not task.wifi_ssid or not task.wifi_password or not task.admin_password:
            generated = await ConfigEngine.auto_generate_passwords()
            if not task.wifi_ssid:
                task.wifi_ssid = generated["wifi_ssid"]
                device_data["wifi_ssid"] = task.wifi_ssid
            if not task.wifi_password:
                task.wifi_password = generated["wifi_password"]
                device_data["wifi_password"] = task.wifi_password
            if not task.admin_password:
                task.admin_password = generated["admin_password"]
                device_data["new_admin_password"] = task.admin_password

        if on_progress:
            on_progress(f"Connecting to {task.device_ip}...")

        result = await ConfigEngine.configure_device(task)

        if result.router_info:
            device_data["brand"] = result.router_info.brand
            device_data["model"] = result.router_info.model
            device_data["firmware_version"] = result.router_info.firmware_version
            device_data["mac_address"] = result.router_info.mac_address

        if result.config_applied:
            device_data["dhcp_mode"] = "disabled" if task.disable_dhcp else "enabled"
            device_data["bridge_mode"] = task.enable_bridge
            device_data["wifi_enabled"] = True
            device_data["ip_address"] = task.device_ip

            if task.admin_username:
                device_data["admin_user"] = task.admin_username
            if task.admin_password:
                device_data["admin_password"] = task.admin_password

        if result.status.value == "success":
            device = None
            if device_data.get("id"):
                device = await DeviceService.get_by_id(session, device_data["id"])

            if not device:
                device_data.setdefault("name", f"{result.router_info.model or task.brand} @ {task.device_ip}")
                device = await DeviceService.create(session, device_data)
            else:
                device = await DeviceService.update(session, device_data["id"], device_data)

            if device and result.config_applied:
                baseline = Baseline(
                    device_id=device.id,
                    label="Post-setup baseline",
                    full_config=result.config_applied.get("config", {}),
                    running_state=result.config_applied.get("state", {}),
                    triggered_by="auto-setup",
                )
                session.add(baseline)
                await session.commit()

            result.task.device_id = device.id if device else None

        return result

    @staticmethod
    async def setup_bulk(
        session: AsyncSession,
        devices_data: list[dict],
        max_concurrent: int = 5,
        on_progress: Callable[[str, int, int], None] = None,
    ) -> list[ConfigTaskResult]:
        results = []
        total = len(devices_data)

        for i, batch in enumerate(_batch(devices_data, max_concurrent)):
            tasks = []
            for d in batch:
                t = ConfigTask(
                    device_ip=d.get("ip_address", ""),
                    device_id=d.get("id"),
                    brand=d.get("brand", "unknown"),
                    username=d.get("admin_username", d.get("username", "admin")),
                    password=d.get("current_password", "admin"),
                    ssh_port=d.get("ssh_port", 22),
                    web_port=d.get("web_port", 80),
                    wifi_ssid=d.get("wifi_ssid", ""),
                    wifi_password=d.get("wifi_password", ""),
                    admin_password=d.get("admin_password", d.get("new_admin_password", "")),
                    admin_username=d.get("admin_username", "admin"),
                    disable_dhcp=d.get("disable_dhcp", True),
                    enable_bridge=d.get("enable_bridge", True),
                    commands=d.get("commands", []),
                    template_variables=d.get("template_variables", {}),
                )

                if not t.wifi_ssid or not t.wifi_password or not t.admin_password:
                    generated = await ConfigEngine.auto_generate_passwords()
                    if not t.wifi_ssid:
                        t.wifi_ssid = generated["wifi_ssid"]
                    if not t.wifi_password:
                        t.wifi_password = generated["wifi_password"]
                    if not t.admin_password:
                        t.admin_password = generated["admin_password"]

                tasks.append(t)

            import asyncio
            batch_results = await asyncio.gather(*[
                ConfigEngine.configure_device(t) for t in tasks
            ])

            for result in batch_results:
                results.append(result)
                if on_progress:
                    on_progress(
                        result.task.device_ip,
                        len(results),
                        total,
                    )

        return results

    @staticmethod
    async def run_action(
        device_id: str,
        connection: dict,
        action: str,
        params: dict | None = None,
    ) -> dict:
        conn = RouterConnection(
            host=connection["host"],
            port=connection.get("ssh_port", 22),
            username=connection.get("username", "admin"),
            password=connection.get("password", ""),
            web_port=connection.get("web_port", 80),
        )
        driver = DriverFactory.create(connection.get("brand", "generic"), conn)

        connected = await driver.connect()
        if not connected:
            return {"success": False, "error": "Failed to connect"}

        result = None
        try:
            if action == "reboot":
                result = await driver.reboot()
            elif action == "factory_reset":
                result = await driver.factory_reset()
            elif action == "backup_config":
                result = await driver.backup_config()
            elif action == "get_connected_clients":
                result = await driver.get_connected_clients()
            elif action == "wifi_on":
                result = await driver.set_wifi_state(True)
            elif action == "wifi_off":
                result = await driver.set_wifi_state(False)
            elif action == "set_wifi":
                result = await driver.set_wifi(WiFiConfig(**params))
            elif action == "set_admin_password":
                result = await driver.set_admin_password(AdminConfig(**params))
            elif action == "set_dhcp":
                result = await driver.set_dhcp(DHCPConfig(**params))
            elif action == "run_command":
                result = await driver.run_custom_command(params.get("command", ""))
            else:
                return {"success": False, "error": f"Unknown action: {action}"}

            await driver.disconnect()

            return {
                "success": result.status.value == "success",
                "action": action,
                "message": result.message,
                "output": getattr(result, "output", ""),
                "data": getattr(result, "data", None),
                "duration_ms": getattr(result, "duration_ms", 0),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


def _batch(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]
