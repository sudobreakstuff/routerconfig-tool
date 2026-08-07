from __future__ import annotations

import asyncio
import re
import time

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


class TPLinkDriver(RouterDriver):

    @property
    def brand(self) -> str:
        return "TP-Link"

    @property
    def capabilities(self) -> list[RouterCapabilities]:
        return [RouterCapabilities.HTTP_ADMIN, RouterCapabilities.SSH]

    async def _ssh_execute(self, command: str) -> str:
        if not self._ssh_client:
            raise RuntimeError("Not connected")
        stdin, stdout, stderr = self._ssh_client.exec_command(command, timeout=self.connection.timeout)
        exit_status = stdout.channel.recv_exit_status()
        output = stdout.read().decode(errors="replace").strip()
        err = stderr.read().decode(errors="replace").strip()
        if exit_status != 0 and err:
            raise RuntimeError(err)
        return output

    async def _http_post(self, path: str, data: dict) -> dict:
        import httpx
        url = f"{self.connection.web_protocol}://{self.connection.host}:{self.connection.web_port}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=self.connection.timeout, verify=False) as client:
            resp = await client.post(url, data=data)
            resp.raise_for_status()
            try:
                return resp.json()
            except Exception:
                return {"raw": resp.text}

    async def _http_request(self, method: str, path: str, data: dict | None = None) -> dict:
        import httpx
        url = f"{self.connection.web_protocol}://{self.connection.host}:{self.connection.web_port}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=self.connection.timeout, verify=False) as client:
            resp = await client.request(method, url, data=data)
            resp.raise_for_status()
            try:
                return resp.json()
            except Exception:
                return {"raw": resp.text}

    async def connect(self) -> bool:
        try:
            await self.http_login()
            return True
        except Exception:
            pass

        try:
            from core.ssh_compat import create_ssh_client
            self._ssh_client = create_ssh_client()
            self._ssh_client.connect(
                self.connection.host,
                port=self.connection.port,
                username=self.connection.username,
                password=self.connection.password,
                timeout=self.connection.timeout,
            )
            return True
        except Exception:
            return False

    async def http_login(self) -> bool:
        try:
            import httpx
            url = f"{self.connection.web_protocol}://{self.connection.host}:{self.connection.web_port}"
            async with httpx.AsyncClient(timeout=self.connection.timeout, verify=False) as client:
                resp = await client.post(
                    f"{url}/cgi-bin/luci/;stok=/login?form=login",
                    data={"username": self.connection.username, "password": self.connection.password},
                )
                if "stok=" in resp.text:
                    match = re.search(r'stok=([^"\'&\s]+)', resp.text)
                    if match:
                        self._stok = match.group(1)
                        self._http_client = client
                        return True

                resp2 = await client.post(
                    f"{url}/cgi-bin/luci/admin/login",
                    data={"username": self.connection.username, "password": self.connection.password},
                )
                if "Set-Cookie" in str(resp2.headers) or resp2.status_code == 302:
                    self._http_client = client
                    return True

                resp3 = await client.get(f"{url}/userRpm/LoginRpm.htm?Save=Save")
                resp4 = await client.post(
                    f"{url}/userRpm/LoginRpm.htm",
                    data={
                        "username": self.connection.username,
                        "password": self.connection.password,
                        "Save": "Save",
                    },
                    headers={"Referer": f"{url}/userRpm/LoginRpm.htm"},
                )
                if "Set-Cookie" in str(resp4.headers) or "/userRpm" in resp4.text:
                    self._http_client = client
                    return True

            return False
        except Exception:
            return False

    async def disconnect(self) -> None:
        if self._ssh_client:
            self._ssh_client.close()
            self._ssh_client = None
        if self._http_client:
            self._http_client = None

    async def is_reachable(self) -> bool:
        result = await self.ping_target(self.connection.host)
        return result.status == ActionStatus.SUCCESS

    async def get_info(self) -> RouterInfo:
        try:
            data = await self._http_request("GET", "userRpm/StatusRpm.htm")
            text = data.get("raw", "")

            model = "unknown"
            fw = ""
            mac = ""
            model_match = re.search(r'Model\s*[：:]\s*([^<\n]+)', text)
            if model_match:
                model = model_match.group(1).strip()
            fw_match = re.search(r'Firmware\s*Version\s*[：:]\s*([^<\n]+)', text)
            if fw_match:
                fw = fw_match.group(1).strip()
            mac_match = re.search(r'([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}', text)
            if mac_match:
                mac = mac_match.group(0)

            return RouterInfo(
                brand="tplink",
                model=model,
                firmware_version=fw,
                mac_address=mac,
                capabilities=self.capabilities,
            )
        except Exception:
            return RouterInfo(brand="tplink", model="unknown")

    async def get_running_config(self) -> dict:
        try:
            data = await self._http_request("GET", "userRpm/BakRestoreRpm.htm")
            return {"raw": data.get("raw", ""), "format": "tplink-web"}
        except Exception:
            try:
                if self._ssh_client:
                    out = await self._ssh_execute("uci export")
                    return {"raw": out, "format": "openwrt-uci"}
            except Exception:
                pass
            return {"error": "Could not retrieve config"}

    async def get_running_state(self) -> RouterState:
        try:
            data = await self._http_request("GET", "userRpm/StatusRpm.htm")
            text = data.get("raw", "")

            dhcp_enabled = "DHCP Server" in text and "Enable" in text
            wifi_enabled = "Wireless" in text and ("Enable" in text or "Running" in text)

            ssids = []
            ssid_match = re.search(r'SSID\s*[：:]\s*([^<\n]+)', text)
            if ssid_match:
                ssids.append({"ssid": ssid_match.group(1).strip(), "band": "2.4ghz"})

            return RouterState(
                is_online=True,
                dhcp_enabled=dhcp_enabled,
                wifi_enabled=wifi_enabled,
                bridge_mode=False,
                ssids=ssids,
            )
        except Exception:
            return RouterState(is_online=False)

    async def apply_config_commands(self, commands: list[str]) -> ActionResult:
        start = time.time()
        output = []
        try:
            if self._ssh_client:
                for cmd in commands:
                    try:
                        out = await self._ssh_execute(cmd)
                        output.append(f"$ {cmd}\n{out}")
                    except Exception as e:
                        output.append(f"# Error: {e}")
            else:
                output.append("# SSH not available; use web admin directly")
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
        start = time.time()
        try:
            data = {
                "Save": "Save",
                "ssid": config.ssid,
                "wlEnbl": "on" if config.enabled else "off",
                "wpapsk": config.password,
                "encrtype": "3",
                "authtype": "3",
            }
            await self._http_post("userRpm/WlanNetworkRpm.htm", data)
            elapsed = (time.time() - start) * 1000
            return ActionResult(
                action="set_wifi",
                status=ActionStatus.SUCCESS,
                data={"ssid": config.ssid},
                duration_ms=elapsed,
            )
        except Exception as e:
            return ActionResult(
                action="set_wifi",
                status=ActionStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    async def set_admin_password(self, config: AdminConfig) -> ActionResult:
        start = time.time()
        try:
            data = {
                "Save": "Save",
                "oldpasswd": self.connection.password,
                "passwd1": config.password,
                "passwd2": config.password,
            }
            await self._http_post("userRpm/ChangeLoginPwdRpm.htm", data)
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
        start = time.time()
        try:
            data = {
                "Save": "Save",
                "dhcpEnbl": "on" if config.enabled else "off",
            }
            if config.enabled:
                data.update({
                    "startip": config.start_ip,
                    "endip": config.end_ip,
                    "leasetime": str(config.lease_time),
                })
            await self._http_post("userRpm/LanDhcpServerRpm.htm", data)
            elapsed = (time.time() - start) * 1000
            return ActionResult(
                action="set_dhcp",
                status=ActionStatus.SUCCESS,
                duration_ms=elapsed,
            )
        except Exception as e:
            return ActionResult(
                action="set_dhcp",
                status=ActionStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    async def set_bridge_mode(self, enabled: bool) -> ActionResult:
        start = time.time()
        try:
            data = {
                "Save": "Save",
                "wanType": "bridge" if enabled else "dhcp",
            }
            await self._http_post("userRpm/WanCfgRpm.htm", data)
            elapsed = (time.time() - start) * 1000
            return ActionResult(
                action="set_bridge_mode",
                status=ActionStatus.SUCCESS,
                duration_ms=elapsed,
            )
        except Exception as e:
            return ActionResult(
                action="set_bridge_mode",
                status=ActionStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    async def reboot(self) -> ActionResult:
        try:
            await self._http_post("userRpm/SysRebootRpm.htm", {"Reboot": "Reboot"})
            return ActionResult(action="reboot", status=ActionStatus.SUCCESS, message="Rebooting")
        except Exception:
            try:
                if self._ssh_client:
                    await self._ssh_execute("reboot")
                    return ActionResult(action="reboot", status=ActionStatus.SUCCESS, message="Rebooting")
            except Exception:
                return ActionResult(action="reboot", status=ActionStatus.SUCCESS, message="Reboot command sent (connection lost)")

    async def factory_reset(self) -> ActionResult:
        try:
            await self._http_post("userRpm/RestoreFactoryDefaultRpm.htm", {"RestoreFactory": "1"})
            return ActionResult(action="factory_reset", status=ActionStatus.SUCCESS, message="Factory reset initiated")
        except Exception:
            try:
                if self._ssh_client:
                    await self._ssh_execute("firstboot && reboot")
                    return ActionResult(action="factory_reset", status=ActionStatus.SUCCESS, message="Factory reset initiated")
            except Exception:
                return ActionResult(action="factory_reset", status=ActionStatus.SUCCESS, message="Reset command sent (connection lost)")

    async def set_wifi_state(self, enabled: bool) -> ActionResult:
        try:
            data = {"wlEnbl": "on" if enabled else "off"}
            await self._http_post("userRpm/WlanNetworkRpm.htm", data)
            return ActionResult(action="set_wifi_state", status=ActionStatus.SUCCESS, message=f"WiFi {'enabled' if enabled else 'disabled'}")
        except Exception as e:
            return ActionResult(action="set_wifi_state", status=ActionStatus.FAILED, error=str(e))

    async def get_connected_clients(self) -> ActionResult:
        try:
            data = await self._http_request("GET", "userRpm/AssignedIpAddrListRpm.htm")
            text = data.get("raw", "")
            clients = []
            for line in text.split("\n"):
                if re.search(r'\d+\.\d+\.\d+\.\d+', line):
                    clients.append({"raw": line.strip()})
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
                error="SSH not available for custom commands on this TP-Link device",
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
