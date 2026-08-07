from __future__ import annotations

import asyncio
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


def _split_cli(command: str) -> list[str]:
    """Split a RouterOS CLI command honoring quoted values and [find ...] groups."""
    tokens: list[str] = []
    current = ""
    quote = None
    bracket = 0
    i = 0
    n = len(command)
    while i < n:
        ch = command[i]
        if quote:
            if ch == quote:
                quote = None
            else:
                current += ch
        elif ch in ('"', "'"):
            quote = ch
        elif ch == "[":
            bracket += 1
            current += ch
        elif ch == "]":
            bracket -= 1
            current += ch
        elif ch.isspace() and bracket == 0:
            if current:
                tokens.append(current)
                current = ""
        else:
            current += ch
        i += 1
    if current:
        tokens.append(current)
    return tokens


def _format_print(records: list[dict], detail: bool = False) -> str:
    """Format API print records like CLI text so existing parsers keep working."""
    if detail:
        out = []
        for r in records:
            parts = []
            for k, v in r.items():
                if k in (".id", "id"):
                    continue
                parts.append(f"{k}={v}")
            out.append(" ".join(parts))
        return "\n".join(out)
    out = []
    for r in records:
        for k, v in r.items():
            if k in (".id", "id"):
                continue
            out.append(f"{k}: {v}")
        out.append("")
    return "\n".join(out).rstrip()


class MikroTikDriver(RouterDriver):

    @property
    def brand(self) -> str:
        return "MikroTik"

    @property
    def capabilities(self) -> list[RouterCapabilities]:
        return [RouterCapabilities.SSH, RouterCapabilities.API, RouterCapabilities.HTTP_ADMIN, RouterCapabilities.WINBOX]

    async def _ssh_execute(self, command: str) -> str:
        import asyncio
        winbox = getattr(self, "_winbox", None)
        if winbox is not None:
            return await asyncio.get_event_loop().run_in_executor(
                None, self._winbox_execute_sync, command
            )
        if getattr(self, "_api", None):
            return await self._api_execute(command)
        if not self._ssh_client:
            raise RuntimeError("Not connected")
        return await asyncio.get_event_loop().run_in_executor(
            None, self._ssh_execute_sync, command
        )

    def _winbox_execute_sync(self, command: str) -> str:
        return self._winbox.exec_command(command, timeout=min(self.connection.timeout, 15))

    def _ssh_execute_sync(self, command: str) -> str:
        stdin, stdout, stderr = self._ssh_client.exec_command(command, timeout=min(self.connection.timeout, 15))
        try:
            exit_status = stdout.channel.recv_exit_status()
        except Exception:
            exit_status = -1
        output = stdout.read().decode(errors="replace").strip()
        return output

    async def _api_execute(self, command: str) -> str:
        """Execute a RouterOS CLI command through the API instead of SSH.

        Translates common CLI syntax (paths with spaces, `print`, `set/add/
        remove/enable/disable`, `[find ...]` selectors, `=key=value` args) into
        API sentences and formats replies as CLI-like text so existing parsing
        keeps working.
        """
        from core.routeros_api import RouterOSAPIError

        api = self._api
        if api is None:
            raise RuntimeError("Not connected via API")

        cmd = command.strip()
        if not cmd:
            return ""

        # /export compact hide-sensitive  ->  special
        if cmd.startswith("/export"):
            records = await api.call("/export")
            lines = []
            for r in records:
                ret = r.get("ret", "")
                if ret:
                    lines.append(ret)
            return "\n".join(lines)

        tokens = _split_cli(cmd)
        raw_path = [t for t in tokens if not t.startswith("=") and not t.startswith("[") and "=" not in t]
        # `print detail` -> `detail` is a CLI flag, not part of the API path.
        if len(raw_path) >= 2 and raw_path[-1] == "detail" and raw_path[-2] == "print":
            raw_path = raw_path[:-1]
        path = raw_path
        action = path[-1] if path else ""
        base = "/".join(p.lstrip("/") for p in path[:-1])
        args: dict = {}
        for t in tokens:
            if t.startswith("="):
                kv = t[1:]
                if "=" in kv:
                    k, _, v = kv.partition("=")
                    args[k] = v.strip('"')
                else:
                    args[kv] = ""
        query: dict = {}
        for t in tokens:
            if t.startswith("["):
                inner = t[1:].rstrip("]").strip()
                if inner in ("find", ""):
                    continue
                body = inner[5:].strip() if inner.startswith("find") else inner
                for seg in _split_cli(body):
                    if seg.startswith("="):
                        kv = seg[1:]
                    else:
                        kv = seg
                    if "=" in kv:
                        k, _, v = kv.partition("=")
                        query[k] = v.strip('"')
                    else:
                        query[kv] = ""

        if not base and action in ("login",):
            return ""

        if action == "print":
            records = await api.call(f"/{base}/print" if base else "/print", **query)
            return _format_print(records, detail=("detail" in args))
        elif action in ("add", "set", "remove", "enable", "disable", "unset"):
            ids: list[str] | None = None
            if "numbers" in args:
                ids = [args["numbers"]]
            elif query or "[find" in cmd:
                ids = await self._api_find_ids(base, query)
            api_path = f"/{base}/{action}"
            params = {k: v for k, v in args.items() if k != "numbers"}
            if ids and len(ids) == 1 and action in ("enable", "disable", "remove"):
                params["numbers"] = ids[0]
            elif ids:
                params["numbers"] = ",".join(ids)
            try:
                await api.call(api_path, **params)
            except RouterOSAPIError as e:
                if "already" in str(e).lower():
                    return ""
                raise
            return ""
        else:
            try:
                await api.call("/" + "/".join(p.lstrip("/") for p in path))
            except RouterOSAPIError as e:
                if "already" in str(e).lower():
                    return ""
                raise
            return ""

    async def _api_find_ids(self, base: str, query: dict) -> list[str]:
        records = await self._api.call(f"/{base}/print", **query)
        return [r.get(".id") or r.get("id") for r in records if r.get(".id") or r.get("id")]

    async def connect(self) -> bool:
        from core.ssh_compat import create_ssh_client
        try:
            self._ssh_client = create_ssh_client()
            if self.connection.jump_host:
                jump = create_ssh_client()
                jump.connect(
                    self.connection.jump_host,
                    port=self.connection.jump_port or 22,
                    username=self.connection.jump_username,
                    password=self.connection.jump_password,
                    timeout=self.connection.timeout,
                )
                transport = jump.get_transport()
                if transport is None:
                    return False
                dest = (self.connection.host, self.connection.port)
                channel = transport.open_channel("direct-tcpip", dest, ("127.0.0.1", 0))
                self._ssh_client.connect(
                    self.connection.host,
                    port=self.connection.port,
                    username=self.connection.username,
                    password=self.connection.password,
                    sock=channel,
                    timeout=self.connection.timeout,
                )
                self._jump_client = jump
            else:
                self._ssh_client.connect(
                    self.connection.host,
                    port=self.connection.port,
                    username=self.connection.username,
                    password=self.connection.password,
                    timeout=self.connection.timeout,
                )
            return True
        except Exception:
            self._ssh_client = None

        if await self._try_api_connect():
            return True

        return await self._try_winbox_connect()

    async def _try_winbox_connect(self) -> bool:
        """Fall back to the WinBox terminal protocol (port 8291) when SSH/API fail.

        WinBox is the management port MikroTik exposes by default, so routers
        reachable through the WinBox app (but not via SSH/API) still work.
        """
        try:
            import asyncio
            from core.winbox_terminal import WinboxTerminalClient
            client = WinboxTerminalClient(
                self.connection.host,
                port=self.connection.winbox_port,
                timeout=min(self.connection.timeout, 10),
            )
            connected = await asyncio.get_event_loop().run_in_executor(
                None, client.connect
            )
            if connected is False:
                raise RuntimeError("connect returned False")
            await asyncio.get_event_loop().run_in_executor(
                None,
                client.authenticate,
                self.connection.username,
                self.connection.password,
            )
            opened = await asyncio.get_event_loop().run_in_executor(
                None,
                client.open_terminal,
                self.connection.password,
                120,
                40,
            )
            if not opened:
                client.close()
                raise RuntimeError("failed to open terminal")
            self._winbox = client
            return True
        except Exception:
            wb = getattr(self, "_winbox", None)
            if wb is not None:
                try:
                    wb.close()
                except Exception:
                    pass
            self._winbox = None
            return False

    async def _try_api_connect(self) -> bool:
        """Fall back to the RouterOS API (8728 plain / 8729 TLS) when SSH fails."""
        from core.routeros_api import RouterOSAPI

        for port, use_ssl in ((8728, False), (8729, True)):
            api = RouterOSAPI(
                self.connection.host,
                username=self.connection.username,
                password=self.connection.password,
                port=port,
                use_ssl=use_ssl,
                timeout=min(self.connection.timeout, 10),
            )
            try:
                await api.connect()
                self._api = api
                self._api_port = port
                return True
            except Exception:
                continue
        self._api = None
        return False

    async def disconnect(self) -> None:
        if self._ssh_client:
            self._ssh_client.close()
            self._ssh_client = None
        if hasattr(self, "_jump_client") and self._jump_client:
            self._jump_client.close()
        api = getattr(self, "_api", None)
        if api:
            try:
                await api.close()
            except Exception:
                pass
            self._api = None
        wb = getattr(self, "_winbox", None)
        if wb is not None:
            try:
                import asyncio
                await asyncio.get_event_loop().run_in_executor(None, wb.close)
            except Exception:
                pass
            self._winbox = None

    async def is_reachable(self) -> bool:
        result = await self.ping_target(self.connection.host)
        return result.status == ActionStatus.SUCCESS

    async def get_info(self) -> RouterInfo:
        try:
            identity = await self._ssh_execute("/system identity print")
            resource = await self._ssh_execute("/system resource print")
            routerboard = await self._ssh_execute("/system routerboard print")

            lines = resource.split("\n")
            version = ""
            uptime = ""
            for line in lines:
                if "version:" in line:
                    version = line.split(":")[-1].strip()
                if "uptime:" in line:
                    uptime = line.split("uptime:")[-1].strip()

            model = ""
            serial = ""
            for line in routerboard.split("\n"):
                if "model:" in line:
                    model = line.split(":")[-1].strip()
                if "serial-number:" in line:
                    serial = line.split(":")[-1].strip()

            mac = ""
            for line in identity.split("\n"):
                if "mac-address:" in line.lower():
                    mac = line.split(":")[-1].strip()

            return RouterInfo(
                brand="mikrotik",
                model=model,
                firmware_version=version,
                mac_address=mac,
                serial_number=serial,
                uptime=uptime,
                capabilities=self.capabilities,
            )
        except Exception:
            return RouterInfo(brand="mikrotik", model="unknown")

    async def get_running_config(self) -> dict:
        try:
            config = await self._ssh_execute("/export compact hide-sensitive")
            return {"raw": config, "format": "mikrotik-cli"}
        except Exception as e:
            return {"error": str(e)}

    async def get_running_state(self) -> RouterState:
        try:
            dhcp = await self._ssh_execute("/ip dhcp-server print detail")
            dhcp_enabled = "X" not in dhcp and dhcp.strip() != "" and "invalid" not in dhcp.lower()

            wireless = await self._ssh_execute("/interface wireless print detail")
            wifi_enabled = "running" in wireless.lower() or "R " in wireless

            dhcp_client = await self._ssh_execute("/ip dhcp-client print detail")
            bridge_mode = "bound" in dhcp_client.lower()

            ssids = []
            for line in wireless.split("\n"):
                if "ssid=" in line.lower():
                    parts = line.split()
                    ssid_val = ""
                    for p in parts:
                        if p.lower().startswith("ssid="):
                            ssid_val = p.split("=", 1)[1].strip('"')
                    if ssid_val:
                        ssids.append({"ssid": ssid_val, "band": "2.4ghz"})

            return RouterState(
                is_online=True,
                dhcp_enabled=dhcp_enabled,
                wifi_enabled=wifi_enabled,
                bridge_mode=bridge_mode,
                ssids=ssids,
            )
        except Exception:
            return RouterState(is_online=False)

    async def apply_config_commands(self, commands: list[str]) -> ActionResult:
        start = time.time()
        try:
            output_parts = []
            for cmd in commands:
                out = await self._ssh_execute(cmd)
                output_parts.append(f"$ {cmd}\n{out}")
            elapsed = (time.time() - start) * 1000
            return ActionResult(
                action="apply_commands",
                status=ActionStatus.SUCCESS,
                output="\n".join(output_parts),
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
            security_cmds = [
                f'/interface wireless set [find default-name=wlan*] ssid="{config.ssid}"',
                f"/interface wireless security-profiles set [find] mode=dynamic-keys "
                f"authentication-types=wpa2-psk wpa2-pre-shared-key=\"{config.password}\"",
            ]
            if not config.enabled:
                security_cmds.append("/interface wireless disable [find]")
            else:
                security_cmds.append("/interface wireless enable [find]")

            output = []
            for cmd in security_cmds:
                out = await self._ssh_execute(cmd)
                output.append(f"$ {cmd}\n{out}")

            elapsed = (time.time() - start) * 1000
            return ActionResult(
                action="set_wifi",
                status=ActionStatus.SUCCESS,
                output="\n".join(output),
                duration_ms=elapsed,
                data={"ssid": config.ssid},
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
            cmd = f'/user set [find name="{config.username}"] password="{config.password}"'
            out = await self._ssh_execute(cmd)
            elapsed = (time.time() - start) * 1000
            return ActionResult(
                action="set_admin_password",
                status=ActionStatus.SUCCESS,
                output=f"$ {cmd}\n{out}",
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
            if not config.enabled:
                cmds = [
                    "/ip dhcp-server disable [find]",
                    "/ip dhcp-server remove [find]",
                ]
            else:
                cmds = [
                    "/ip dhcp-server enable [find]",
                ]
            output = []
            for cmd in cmds:
                try:
                    out = await self._ssh_execute(cmd)
                    output.append(f"$ {cmd}\n{out}")
                except Exception:
                    pass
            elapsed = (time.time() - start) * 1000
            return ActionResult(
                action="set_dhcp",
                status=ActionStatus.SUCCESS,
                output="\n".join(output),
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
            if enabled:
                cmds = [
                    "/ip dhcp-client add interface=ether1 disabled=no",
                    "/ip firewall nat add chain=srcnat out-interface=ether1 action=masquerade",
                ]
            else:
                cmds = [
                    "/ip dhcp-client remove [find interface=ether1]",
                ]
            output = []
            for cmd in cmds:
                try:
                    out = await self._ssh_execute(cmd)
                    output.append(f"$ {cmd}\n{out}")
                except Exception:
                    pass
            elapsed = (time.time() - start) * 1000
            return ActionResult(
                action="set_bridge_mode",
                status=ActionStatus.SUCCESS,
                output="\n".join(output),
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
            await self._ssh_execute("/system reboot")
            return ActionResult(action="reboot", status=ActionStatus.SUCCESS, message="Rebooting")
        except Exception:
            return ActionResult(action="reboot", status=ActionStatus.SUCCESS, message="Reboot command sent (connection lost)")

    async def factory_reset(self) -> ActionResult:
        try:
            await self._ssh_execute("/system reset-configuration no-defaults=yes skip-backup=yes")
            return ActionResult(action="factory_reset", status=ActionStatus.SUCCESS, message="Factory reset initiated")
        except Exception:
            return ActionResult(action="factory_reset", status=ActionStatus.SUCCESS, message="Reset command sent (connection lost)")

    async def set_wifi_state(self, enabled: bool) -> ActionResult:
        try:
            cmd = "/interface wireless enable [find]" if enabled else "/interface wireless disable [find]"
            await self._ssh_execute(cmd)
            return ActionResult(action="set_wifi_state", status=ActionStatus.SUCCESS, message=f"WiFi {'enabled' if enabled else 'disabled'}")
        except Exception as e:
            return ActionResult(action="set_wifi_state", status=ActionStatus.FAILED, error=str(e))

    async def get_connected_clients(self) -> ActionResult:
        try:
            out = await self._ssh_execute("/ip arp print detail")
            clients = []
            for line in out.split("\n"):
                if "address=" in line.lower():
                    clients.append({"raw": line.strip()})
            return ActionResult(
                action="get_connected_clients",
                status=ActionStatus.SUCCESS,
                data={"clients": clients, "count": len(clients)},
            )
        except Exception as e:
            return ActionResult(action="get_connected_clients", status=ActionStatus.FAILED, error=str(e))

    async def run_custom_command(self, command: str) -> ActionResult:
        start = time.time()
        try:
            out = await self._ssh_execute(command)
            elapsed = (time.time() - start) * 1000
            return ActionResult(
                action="custom_command",
                status=ActionStatus.SUCCESS,
                output=out,
                duration_ms=elapsed,
            )
        except Exception as e:
            return ActionResult(
                action="custom_command",
                status=ActionStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    async def discover_downstream_devices(self) -> list[dict]:
        import re as _re
        from core.mac_vendor import lookup_vendor
        devices = []
        try:
            arp = await self._ssh_execute("/ip arp print detail")
            for line in arp.split("\n"):
                ip = _re.search(r'address=(\d+\.\d+\.\d+\.\d+)', line, _re.IGNORECASE)
                mac = _re.search(r'mac-address=([0-9a-fA-F:]+)', line, _re.IGNORECASE)
                if ip:
                    m = mac.group(1) if mac else ""
                    devices.append({"ip": ip.group(1), "mac": m, "mac_vendor": lookup_vendor(m), "source": "arp"})
        except Exception: pass

        try:
            leases = await self._ssh_execute("/ip dhcp-server lease print detail")
            for line in leases.split("\n"):
                ip = _re.search(r'address=(\d+\.\d+\.\d+\.\d+)', line, _re.IGNORECASE)
                mac = _re.search(r'mac-address=([0-9a-fA-F:]+)', line, _re.IGNORECASE)
                if ip:
                    m = mac.group(1) if mac else ""
                    devices.append({"ip": ip.group(1), "mac": m, "mac_vendor": lookup_vendor(m), "source": "dhcp"})
        except Exception: pass

        try:
            hosts = await self._ssh_execute("/ip hotspot host print detail 2>/dev/null")
            for line in hosts.split("\n"):
                ip = _re.search(r'address=(\d+\.\d+\.\d+\.\d+)', line, _re.IGNORECASE)
                mac = _re.search(r'mac-address=([0-9a-fA-F:]+)', line, _re.IGNORECASE)
                if ip:
                    m = mac.group(1) if mac else ""
                    devices.append({"ip": ip.group(1), "mac": m, "mac_vendor": lookup_vendor(m), "source": "hotspot"})
        except Exception: pass

        seen = set()
        unique = []
        for d in devices:
            k = d["ip"] or d["mac"]
            if k and k not in seen and not d.get("ip","").startswith("0.") and not d.get("ip","").startswith("255."):
                seen.add(k)
                unique.append(d)
        return unique[:50]

    async def list_aliases(self) -> list[dict]:
        aliases = []
        try:
            out = await self._ssh_execute("/ip address print detail")
            for line in out.split("\n"):
                if "address=" in line.lower():
                    addr = re.search(r'address=([\d.]+/\d+)', line)
                    iface = re.search(r'interface=(\S+)', line)
                    dynamic = "dynamic=" in line.lower() and "true" in line.lower()
                    if addr and not dynamic:
                        aliases.append({
                            "ip": addr.group(1),
                            "interface": iface.group(1) if iface else "unknown",
                            "config_line": line.strip(),
                        })
        except Exception: pass
        return aliases

    async def add_alias(self, ip: str, netmask: str = "255.255.255.0", interface: str = "ether2") -> ActionResult:
        try:
            cidr = sum(bin(int(x)).count("1") for x in netmask.split("."))
            cmd = f"/ip address add address={ip}/{cidr} interface={interface}"
            await self._ssh_execute(cmd)
            return ActionResult(action="add_alias", status=ActionStatus.SUCCESS,
                               message=f"Added address {ip}/{cidr} on {interface}")
        except Exception as e:
            if "already" in str(e).lower() or "exists" in str(e).lower():
                return ActionResult(action="add_alias", status=ActionStatus.SUCCESS,
                                   message=f"Address {ip} already exists")
            return ActionResult(action="add_alias", status=ActionStatus.FAILED, error=str(e))

    async def remove_alias(self, ip: str) -> ActionResult:
        try:
            out = await self._ssh_execute("/ip address print detail")
            for line in out.split("\n"):
                if f"address={ip}/" in line.lower() or f"address={ip}" in line:
                    num = re.search(r'^\s*(\d+)', line)
                    if num:
                        await self._ssh_execute(f"/ip address remove {num.group(1)}")
                        return ActionResult(action="remove_alias", status=ActionStatus.SUCCESS,
                                           message=f"Removed address {ip}")
            return ActionResult(action="remove_alias", status=ActionStatus.SUCCESS,
                               message=f"Address {ip} not found")
        except Exception as e:
            return ActionResult(action="remove_alias", status=ActionStatus.FAILED, error=str(e))
