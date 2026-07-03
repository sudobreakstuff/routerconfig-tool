from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime

from core.drivers.base import (
    RouterDriver,
    RouterConnection,
    RouterInfo,
    WiFiConfig,
    AdminConfig,
    DHCPConfig,
    ActionResult,
    ActionStatus,
)
from core.drivers.factory import DriverFactory
from core.password_gen import generate_wifi_password, generate_admin_password, generate_ssid


@dataclass
class ConfigTask:
    device_ip: str
    device_id: str | None = None
    brand: str = "unknown"
    username: str = "admin"
    password: str = "admin"
    ssh_port: int = 22
    web_port: int = 80
    wifi_ssid: str = ""
    wifi_password: str = ""
    admin_password: str = ""
    admin_username: str = "admin"
    disable_dhcp: bool = True
    enable_bridge: bool = True
    commands: list[str] = field(default_factory=list)
    template_variables: dict = field(default_factory=dict)


@dataclass
class ConfigTaskResult:
    task: ConfigTask
    status: ActionStatus
    router_info: RouterInfo | None = None
    config_applied: dict | None = None
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
    output_log: list[str] = field(default_factory=list)


class ConfigEngine:

    @staticmethod
    def create_connection(task: ConfigTask) -> RouterConnection:
        return RouterConnection(
            host=task.device_ip,
            port=task.ssh_port,
            username=task.username,
            password=task.password,
            web_port=task.web_port,
        )

    @staticmethod
    async def auto_generate_passwords() -> dict:
        return {
            "wifi_ssid": generate_ssid(prefix="JENNY"),
            "wifi_password": generate_wifi_password(),
            "admin_password": generate_admin_password(),
        }

    @staticmethod
    async def configure_device(task: ConfigTask) -> ConfigTaskResult:
        start = time.time()
        result = ConfigTaskResult(task=task, status=ActionStatus.RUNNING)

        connection = ConfigEngine.create_connection(task)
        driver = DriverFactory.create(task.brand, connection)

        try:
            connected = await driver.connect()
            if not connected:
                result.status = ActionStatus.FAILED
                result.errors.append("Failed to connect to device")
                result.duration_ms = (time.time() - start) * 1000
                return result

            result.output_log.append(f"[OK] Connected to {task.device_ip}")

            info = await driver.get_info()
            result.router_info = info
            result.output_log.append(f"[INFO] Brand: {info.brand}, Model: {info.model}, FW: {info.firmware_version}")

            if task.admin_password:
                admin_config = AdminConfig(
                    username=task.admin_username,
                    password=task.admin_password,
                )
                admin_result = await driver.set_admin_password(admin_config)
                result.output_log.append(f"[{'OK' if admin_result.status == ActionStatus.SUCCESS else 'FAIL'}] Admin password: {admin_result.status}")
                if admin_result.status != ActionStatus.SUCCESS:
                    result.errors.append(f"Admin password change failed: {admin_result.error}")

            if task.wifi_ssid and task.wifi_password:
                wifi_config = WiFiConfig(
                    ssid=task.wifi_ssid,
                    password=task.wifi_password,
                    enabled=True,
                )
                wifi_result = await driver.set_wifi(wifi_config)
                result.output_log.append(f"[{'OK' if wifi_result.status == ActionStatus.SUCCESS else 'FAIL'}] WiFi config: {wifi_result.status}")
                if wifi_result.status != ActionStatus.SUCCESS:
                    result.errors.append(f"WiFi config failed: {wifi_result.error}")

            if task.disable_dhcp:
                dhcp_config = DHCPConfig(enabled=False)
                dhcp_result = await driver.set_dhcp(dhcp_config)
                result.output_log.append(f"[{'OK' if dhcp_result.status == ActionStatus.SUCCESS else 'FAIL'}] DHCP disable: {dhcp_result.status}")
                if dhcp_result.status != ActionStatus.SUCCESS:
                    result.errors.append(f"DHCP disable failed: {dhcp_result.error}")

            if task.enable_bridge:
                bridge_result = await driver.set_bridge_mode(True)
                result.output_log.append(f"[{'OK' if bridge_result.status == ActionStatus.SUCCESS else 'FAIL'}] Bridge mode: {bridge_result.status}")
                if bridge_result.status != ActionStatus.SUCCESS:
                    result.errors.append(f"Bridge mode failed: {bridge_result.error}")

            if task.commands:
                cmd_result = await driver.apply_config_commands(task.commands)
                result.output_log.append(f"[{'OK' if cmd_result.status == ActionStatus.SUCCESS else 'FAIL'}] Custom commands: {cmd_result.status}")
                if cmd_result.status != ActionStatus.SUCCESS:
                    result.errors.append(f"Custom commands failed: {cmd_result.error}")

            running_config = await driver.get_running_config()
            running_state = await driver.get_running_state()

            result.config_applied = {
                "config": running_config,
                "state": {
                    "dhcp_enabled": running_state.dhcp_enabled,
                    "wifi_enabled": running_state.wifi_enabled,
                    "bridge_mode": running_state.bridge_mode,
                    "ssids": running_state.ssids,
                },
                "wifi_ssid": task.wifi_ssid,
                "admin_username": task.admin_username,
                "timestamp": datetime.utcnow().isoformat(),
            }

            await driver.disconnect()

            result.status = ActionStatus.SUCCESS if not result.errors else ActionStatus.FAILED
        except Exception as e:
            result.status = ActionStatus.FAILED
            result.errors.append(str(e))
            result.output_log.append(f"[ERROR] {e}")
        finally:
            result.duration_ms = (time.time() - start) * 1000

        return result

    @staticmethod
    async def configure_bulk(tasks: list[ConfigTask], max_concurrent: int = 10) -> list[ConfigTaskResult]:
        semaphore = asyncio.Semaphore(max_concurrent)

        async def run_with_semaphore(task: ConfigTask) -> ConfigTaskResult:
            async with semaphore:
                return await ConfigEngine.configure_device(task)

        results = await asyncio.gather(*[run_with_semaphore(t) for t in tasks])
        return list(results)
