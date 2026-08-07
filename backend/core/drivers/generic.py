from __future__ import annotations

import asyncio
import re
import time
import json

from core.drivers.base import (
    RouterDriver,
    RouterConnection,
    RouterInfo,
    RouterState,
    RouterCapabilities,
    WiFiConfig,
    AdminConfig,
    DHCPConfig,
    ActionResult,
    ActionStatus,
)


class GenericDriver(RouterDriver):

    @property
    def brand(self) -> str:
        return "Generic"

    @property
    def capabilities(self) -> list[RouterCapabilities]:
        caps = [RouterCapabilities.HTTP_ADMIN]
        if self.connection.port == 22:
            caps.append(RouterCapabilities.SSH)
        return caps

    async def _try_ssh_connect(self) -> bool:
        from core.ssh_compat import create_ssh_client
        try:
            self._ssh_client = create_ssh_client()
            self._ssh_client.connect(
                self.connection.host,
                port=self.connection.port,
                username=self.connection.username,
                password=self.connection.password,
                timeout=min(self.connection.timeout, 10),
            )
            return True
        except Exception:
            self._ssh_client = None
            return False

    async def _ssh_execute(self, command: str) -> str:
        if not self._ssh_client:
            raise RuntimeError("Not connected via SSH")
        stdin, stdout, stderr = self._ssh_client.exec_command(command, timeout=self.connection.timeout)
        stdout.channel.recv_exit_status()
        return stdout.read().decode(errors="replace").strip()

    async def connect(self) -> bool:
        if await self._try_ssh_connect():
            return True

        try:
            await self.http_login()
            return True
        except Exception:
            return False

    async def http_login(self) -> bool:
        import httpx
        url = f"{self.connection.web_protocol}://{self.connection.host}:{self.connection.web_port}"

        async with httpx.AsyncClient(timeout=self.connection.timeout, verify=False) as client:
            login_payloads = [
                {"url": f"{url}/login.cgi", "data": {"username": self.connection.username, "password": self.connection.password}},
                {"url": f"{url}/goform/login", "data": {"user": self.connection.username, "pass": self.connection.password}},
                {"url": f"{url}/login", "data": {"username": self.connection.username, "password": self.connection.password}},
                {"url": f"{url}/cgi-bin/luci/admin/login", "data": {"luci_username": self.connection.username, "luci_password": self.connection.password}},
                {"url": f"{url}/api/auth/login", "data": json.dumps({"username": self.connection.username, "password": self.connection.password})},
            ]
            for payload in login_payloads:
                try:
                    resp = await client.post(
                        payload["url"],
                        data=payload["data"],
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
                    if resp.status_code in [200, 302] and "error" not in resp.text.lower():
                        self._http_client = client
                        return True
                except Exception:
                    continue
        return False

    async def disconnect(self) -> None:
        if self._ssh_client:
            self._ssh_client.close()
            self._ssh_client = None

    async def is_reachable(self) -> bool:
        result = await self.ping_target(self.connection.host)
        return result.status == ActionStatus.SUCCESS

    async def get_info(self) -> RouterInfo:
        try:
            if self._ssh_client:
                try:
                    uname = await self._ssh_execute("uname -a 2>/dev/null || cat /proc/version 2>/dev/null")
                except Exception:
                    uname = ""

                try:
                    model = await self._ssh_execute("cat /proc/cpuinfo 2>/dev/null | grep -i model | head -1 || cat /tmp/sysinfo/model 2>/dev/null || echo ''")
                except Exception:
                    model = ""

                return RouterInfo(
                    brand="unknown",
                    model=model.strip() or "unknown",
                    capabilities=[RouterCapabilities.SSH],
                )

            if self._http_client:
                import httpx
                url = f"{self.connection.web_protocol}://{self.connection.host}:{self.connection.web_port}"
                async with httpx.AsyncClient(timeout=10, verify=False) as client:
                    resp = await client.get(f"{url}/")
                    text = resp.text.lower()
                    if "mikrotik" in text:
                        return RouterInfo(brand="mikrotik", model="auto-detected", capabilities=self.capabilities)
                    if "tplink" in text or "tp-link" in text:
                        return RouterInfo(brand="tplink", model="auto-detected", capabilities=self.capabilities)
                    if "ubiquiti" in text or "unifi" in text:
                        return RouterInfo(brand="ubiquiti", model="auto-detected", capabilities=self.capabilities)
                    title_match = re.search(r'<title>([^<]+)</title>', resp.text, re.IGNORECASE)
                    title = title_match.group(1) if title_match else "Unknown Router"
                    return RouterInfo(brand="unknown", model=title[:64], capabilities=self.capabilities)
        except Exception:
            pass

        return RouterInfo(brand="unknown", model="unknown")

    async def get_running_config(self) -> dict:
        return {"raw": "", "format": "generic", "note": "Full config export not available for generic devices"}

    async def get_running_state(self) -> RouterState:
        return RouterState(is_online=True)

    async def apply_config_commands(self, commands: list[str]) -> ActionResult:
        if not self._ssh_client:
            return ActionResult(
                action="apply_commands",
                status=ActionStatus.FAILED,
                error="Generic driver requires SSH connection for command execution",
            )
        start = time.time()
        output = []
        try:
            for cmd in commands:
                out = await self._ssh_execute(cmd)
                output.append(f"$ {cmd}\n{out}")
            elapsed = (time.time() - start) * 1000
            return ActionResult(
                action="apply_commands",
                status=ActionStatus.SUCCESS,
                output="\n".join(output),
                duration_ms=elapsed,
            )
        except Exception as e:
            return ActionResult(
                action="apply_commands",
                status=ActionStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    async def set_wifi(self, config: WiFiConfig) -> ActionResult:
        return ActionResult(
            action="set_wifi",
            status=ActionStatus.FAILED,
            error="WiFi configuration not available for unknown device type. Use custom commands.",
        )

    async def set_admin_password(self, config: AdminConfig) -> ActionResult:
        if not self._ssh_client:
            return ActionResult(
                action="set_admin_password",
                status=ActionStatus.FAILED,
                error="Password change requires SSH. Use custom command: passwd",
            )
        start = time.time()
        try:
            stdin, stdout, stderr = self._ssh_client.exec_command(
                f"echo '{config.username}:{config.password}' | chpasswd 2>/dev/null || "
                f"(echo -e '{config.password}\n{config.password}' | passwd 2>/dev/null)"
            )
            stdout.channel.recv_exit_status()
            elapsed = (time.time() - start) * 1000
            return ActionResult(
                action="set_admin_password",
                status=ActionStatus.SUCCESS,
                duration_ms=elapsed,
            )
        except Exception as e:
            return ActionResult(
                action="set_admin_password",
                status=ActionStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    async def set_dhcp(self, config: DHCPConfig) -> ActionResult:
        return ActionResult(
            action="set_dhcp",
            status=ActionStatus.FAILED,
            error="DHCP configuration not available for unknown device type. Use custom commands.",
        )

    async def set_bridge_mode(self, enabled: bool) -> ActionResult:
        return ActionResult(
            action="set_bridge_mode",
            status=ActionStatus.FAILED,
            error="Bridge mode configuration not available for unknown device type. Use custom commands.",
        )

    async def reboot(self) -> ActionResult:
        if not self._ssh_client:
            return ActionResult(action="reboot", status=ActionStatus.FAILED, error="SSH not available")
        try:
            await self._ssh_execute("reboot")
            return ActionResult(action="reboot", status=ActionStatus.SUCCESS, message="Rebooting")
        except Exception:
            return ActionResult(action="reboot", status=ActionStatus.SUCCESS, message="Reboot command sent (connection lost)")

    async def factory_reset(self) -> ActionResult:
        if not self._ssh_client:
            return ActionResult(action="factory_reset", status=ActionStatus.FAILED, error="SSH not available")
        try:
            await self._ssh_execute("jffs2reset -y && reboot 2>/dev/null || mtd -r erase rootfs_data 2>/dev/null || firstboot && reboot")
            return ActionResult(action="factory_reset", status=ActionStatus.SUCCESS, message="Factory reset initiated")
        except Exception:
            return ActionResult(action="factory_reset", status=ActionStatus.SUCCESS, message="Reset command sent (connection lost)")

    async def set_wifi_state(self, enabled: bool) -> ActionResult:
        if not self._ssh_client:
            return ActionResult(action="set_wifi_state", status=ActionStatus.FAILED, error="SSH not available")
        try:
            action = "up" if enabled else "down"
            await self._ssh_execute(f"ifconfig wlan0 {action} 2>/dev/null || ifconfig ath0 {action} 2>/dev/null")
            return ActionResult(action="set_wifi_state", status=ActionStatus.SUCCESS, message=f"WiFi interface set {action}")
        except Exception as e:
            return ActionResult(action="set_wifi_state", status=ActionStatus.FAILED, error=str(e))

    async def get_connected_clients(self) -> ActionResult:
        if not self._ssh_client:
            return ActionResult(action="get_connected_clients", status=ActionStatus.FAILED, error="SSH not available")
        try:
            out = await self._ssh_execute("arp -a 2>/dev/null || ip neigh show 2>/dev/null")
            clients = [line.strip() for line in out.split("\n") if line.strip()]
            return ActionResult(
                action="get_connected_clients",
                status=ActionStatus.SUCCESS,
                data={"clients": clients, "count": len(clients)},
            )
        except Exception as e:
            return ActionResult(action="get_connected_clients", status=ActionStatus.FAILED, error=str(e))

    async def run_custom_command(self, command: str) -> ActionResult:
        if not self._ssh_client:
            return ActionResult(
                action="custom_command",
                status=ActionStatus.FAILED,
                error="SSH not available",
            )
        start = time.time()
        try:
            out = await self._ssh_execute(command)
            return ActionResult(
                action="custom_command",
                status=ActionStatus.SUCCESS,
                output=out,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return ActionResult(action="custom_command", status=ActionStatus.FAILED, error=str(e))
