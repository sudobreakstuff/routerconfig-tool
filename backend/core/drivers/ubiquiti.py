from __future__ import annotations

import asyncio
import os
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


class UbiquitiDriver(RouterDriver):

    @property
    def brand(self) -> str:
        return "Ubiquiti"

    @property
    def capabilities(self) -> list[RouterCapabilities]:
        return [RouterCapabilities.SSH, RouterCapabilities.HTTP_ADMIN, RouterCapabilities.API]

    async def _ssh_execute(self, command: str) -> str:
        import asyncio
        if not self._ssh_client:
            raise RuntimeError("Not connected")
        return await asyncio.get_event_loop().run_in_executor(
            None, self._ssh_execute_sync, command
        )

    def _ssh_execute_sync(self, command: str) -> str:
        """Blocking SSH execute - runs in thread pool."""
        stdin, stdout, stderr = self._ssh_client.exec_command(command, timeout=min(self.connection.timeout, 15))
        try:
            exit_status = stdout.channel.recv_exit_status()
        except Exception:
            exit_status = -1
        output = stdout.read().decode(errors="replace").strip()
        return output

    async def connect(self) -> bool:
        import paramiko

        # Try SSH first
        try:
            self._ssh_client = paramiko.SSHClient()
            self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self._ssh_client.connect(
                self.connection.host,
                port=self.connection.port,
                username=self.connection.username,
                password=self.connection.password,
                timeout=self.connection.timeout,
                banner_timeout=10,
            )
            return True
        except Exception:
            self._ssh_client = None

        # Try Ubiquiti HTTP API on port 443 (UniFi / UISP devices)
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10, verify=False) as client:
                resp = await client.post(
                    f"https://{self.connection.host}:443/api/auth/login",
                    json={"username": self.connection.username, "password": self.connection.password},
                )
                if resp.status_code == 200:
                    self._http_client = client
                    return True
        except Exception:
            pass

        # Try Ubiquiti web GUI on port 80/443 (EdgeMAX / AirOS)
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10, verify=False) as client:
                resp = await client.post(
                    f"{self.connection.web_protocol}://{self.connection.host}:{self.connection.web_port}/api/login",
                    data={
                        "username": self.connection.username,
                        "password": self.connection.password,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                if resp.status_code in (200, 302):
                    self._http_client = client
                    return True
        except Exception:
            pass

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
        info = RouterInfo(brand="ubiquiti", model="unknown", capabilities=self.capabilities)

        # Try airOS (mca-status outputs comma-separated key=value on a single line)
        try:
            raw = await self._ssh_execute("mca-status 2>/dev/null")
            if raw:
                # Parse comma-separated key=value pairs
                parsed = {}
                for part in raw.split(","):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        parsed[k.strip()] = v.strip()

                info.model = parsed.get("platform", "unknown")
                info.firmware_version = parsed.get("firmwareVersion", "airOS")
                info.mac_address = parsed.get("deviceMac", "")
                info.uptime = parsed.get("uptime", "")

                # If MAC is still unknown, try alternate sources
                if not info.mac_address:
                    try:
                        # /etc/board.hwaddr always contains the MAC on airOS
                        hw = await self._ssh_execute("cat /etc/board.hwaddr 2>/dev/null")
                        if hw.strip():
                            mac_match = re.search(r'([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', hw.strip())
                            if mac_match: info.mac_address = mac_match.group(0)
                    except Exception: pass

                if not info.mac_address:
                    try:
                        ifconfig = await self._ssh_execute("ifconfig eth0 2>/dev/null | grep -i 'hwaddr\\|ether' | head -1")
                        mac_match = re.search(r'([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', ifconfig)
                        if mac_match: info.mac_address = mac_match.group(0)
                    except Exception: pass

                if not info.mac_address:
                    # Last resort: parse from mca-status first field (MAC without key)
                    first_field = raw.split(",")[0].strip()
                    if re.match(r'^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$', first_field):
                        info.mac_address = first_field

                # Also try board info
                try:
                    board = await self._ssh_execute("cat /etc/board.info 2>/dev/null")
                    if board:
                        for line in board.split("\n"):
                            if "=" in line:
                                k, v = line.split("=", 1)
                                k, v = k.strip(), v.strip()
                                if k == "model" and info.model == "unknown":
                                    info.model = f"{v} {parsed.get('platform','')}".strip()
                                if k == "id":
                                    info.model = info.model or v
                except Exception:
                    pass

                # Get serial from board.hwaddr
                try:
                    hw = await self._ssh_execute("cat /etc/board.hwaddr 2>/dev/null")
                    if hw.strip():
                        info.serial_number = hw.strip()
                except Exception:
                    pass

                return info
        except Exception:
            pass

        # Try EdgeOS / EdgeMAX
        try:
            raw = await self._ssh_execute("cat /etc/version 2>/dev/null; show version 2>/dev/null | head -8")
            if "EdgeOS" in raw or "EdgeRouter" in raw or "Vyatta" in raw:
                info.firmware_version = self._extract_line(raw, r'(EdgeOS[^\n]+|v[0-9.]+)') or "EdgeOS"
                info.model = self._extract_line(raw, r'(EdgeRouter[^\s]+|EdgeSwitch[^\s]+|ER[-\w]+)') or "EdgeMAX"
                try:
                    ifcfg = await self._ssh_execute("ifconfig eth0 2>/dev/null | grep -i hwaddr | head -1")
                    m = re.search(r'([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', ifcfg)
                    if m: info.mac_address = m.group(0)
                except Exception: pass
                try:
                    up = await self._ssh_execute("uptime 2>/dev/null"); info.uptime = up.strip()
                except Exception: pass
                return info
        except Exception:
            pass

        # Try generic Linux (UniFi OS)
        try:
            raw = await self._ssh_execute(
                "cat /etc/version 2>/dev/null || uname -a 2>/dev/null; "
                "cat /proc/cpuinfo 2>/dev/null | grep -i 'model\\|hardware' | head -3; "
                "cat /proc/version 2>/dev/null | head -1"
            )
            hw = re.search(r'(?:model|hardware)\s*:\s*(.+)', raw, re.IGNORECASE)
            if hw: info.model = hw.group(1).strip()
            ver = re.search(r'(\d+\.\d+\.\d+)', raw)
            if ver: info.firmware_version = f"Linux {ver.group(1)}"
            try: info.mac_address = self._extract_mac(await self._ssh_execute("ifconfig 2>/dev/null | grep -i 'hwaddr\\|ether' | head -1"))
            except Exception: pass
            try: info.uptime = (await self._ssh_execute("uptime 2>/dev/null")).strip()
            except Exception: pass
        except Exception:
            pass

        return info

    @staticmethod
    def _extract_value(text: str, pattern: str) -> str:
        m = re.search(pattern, text)
        return m.group(0).split("=")[-1].strip() if m else ""

    @staticmethod
    def _extract_line(text: str, pattern: str) -> str:
        m = re.search(pattern, text)
        return m.group(1).strip() if m else ""

    async def get_running_config(self) -> dict:
        configs = {}
        try:
            configs["system.cfg"] = await self._ssh_execute("cat /tmp/system.cfg 2>/dev/null || echo ''")
        except Exception:
            pass
        try:
            configs["config.boot"] = await self._ssh_execute("cat /config/config.boot 2>/dev/null || echo ''")
        except Exception:
            pass
        if not any(v.strip() for v in configs.values()):
            try:
                configs["export"] = await self._ssh_execute("show configuration commands 2>/dev/null || echo ''")
            except Exception:
                pass
        configs["format"] = "ubiquiti"
        return configs

    async def discover_downstream_devices(self, probe_aliases: list[str] | None = None) -> list[dict]:
        from core.mac_vendor import lookup_vendor

        devices = []

        def add_device(ip: str, mac: str, source: str, raw: str = ""):
            if not ip and not mac:
                return
            # Filter bogus IPs
            if ip and (ip.startswith("0.") or ip.startswith("255.") or ip.startswith("8.")):
                return
            m = re.search(r'([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', mac or raw or "")
            full_mac = m.group(0) if m else mac
            devices.append({
                "ip": ip,
                "mac": full_mac,
                "mac_vendor": lookup_vendor(full_mac),
                "source": source,
            })

        # ARP / ip neigh
        try:
            arp = await self._ssh_execute("arp -a 2>/dev/null; ip neigh show 2>/dev/null")
            for line in arp.split("\n"):
                ip = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                mac = re.search(r'([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', line)
                if ip:
                    add_device(ip.group(0), mac.group(0) if mac else "", "arp", line)
        except Exception:
            pass

        # airOS station dump
        try:
            stations = await self._ssh_execute("mca-dump 2>/dev/null | grep -E 'sta|Station'  | head -40")
            for line in stations.split("\n"):
                if line.strip():
                    ip = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                    mac = re.search(r'([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', line)
                    if ip or mac:
                        add_device(ip.group(0) if ip else "", mac.group(0) if mac else "", "mca-dump", line)
        except Exception:
            pass

        # EdgeOS DHCP leases
        try:
            leases = await self._ssh_execute("show dhcp leases 2>/dev/null | head -40")
            for line in leases.split("\n"):
                ip = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                mac = re.search(r'([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', line)
                if ip:
                    add_device(ip.group(0), mac.group(0) if mac else "", "dhcp", line)
        except Exception:
            pass

        # Deduplicate
        seen = set()
        unique = []
        for d in devices:
            key = d["ip"] or d["mac"]
            if key and key not in seen:
                seen.add(key)
                unique.append(d)

        return unique[:50]

    async def list_aliases(self) -> list[dict]:
        """List IP aliases on the device (netconf.X.alias.Y entries)."""
        aliases = []
        try:
            cfg = await self._ssh_execute("cat /tmp/system.cfg 2>/dev/null")
            for line in cfg.split("\n"):
                m = re.search(r'netconf\.(\d+)\.alias\.(\d+)\.ip=(\d+\.\d+\.\d+\.\d+)', line)
                if m:
                    iface_num, alias_num, ip = m.group(1), m.group(2), m.group(3)
                    netmask_match = re.search(rf'netconf\.{iface_num}\.alias\.{alias_num}\.netmask=([\d.]+)', cfg)
                    status_match = re.search(rf'netconf\.{iface_num}\.alias\.{alias_num}\.status=(enabled|disabled)', cfg)
                    aliases.append({
                        "interface": f"netconf.{iface_num}",
                        "alias_number": alias_num,
                        "ip": ip,
                        "netmask": netmask_match.group(1) if netmask_match else "255.255.255.0",
                        "status": status_match.group(1) if status_match else "unknown",
                        "config_line": line.strip(),
                    })
        except Exception:
            pass
        return aliases

    async def add_alias(self, ip: str, netmask: str = "255.255.255.0", interface_num: int = 2) -> ActionResult:
        """Add an IP alias on the device. Defaults to eth0 (netconf.2)."""
        start = time.time()
        try:
            cfg = await self._ssh_execute("cat /tmp/system.cfg 2>/dev/null")
            existing = re.findall(r'netconf\.\d+\.alias\.\d+\.ip=([\d.]+)', cfg)
            if ip in existing:
                ifconfig_cmd = f"ifconfig eth0 {ip} netmask {netmask} up 2>/dev/null || ifconfig eth0 add {ip}/{netmask} 2>/dev/null"
                try: await self._ssh_execute(ifconfig_cmd)
                except: pass
                return ActionResult(action="add_alias", status=ActionStatus.SUCCESS,
                                   message=f"Alias {ip} already exists in config, brought up")

            alias_nums = [int(m) for m in re.findall(rf'netconf\.{interface_num}\.alias\.(\d+)\.', cfg)]
            next_num = max(alias_nums) + 1 if alias_nums else 1

            cmds = [
                f"echo 'netconf.{interface_num}.alias.{next_num}.ip={ip}' >> /tmp/system.cfg",
                f"echo 'netconf.{interface_num}.alias.{next_num}.netmask={netmask}' >> /tmp/system.cfg",
                f"echo 'netconf.{interface_num}.alias.{next_num}.status=enabled' >> /tmp/system.cfg",
                f"cfgmtd -w -p /etc/ 2>/dev/null || true",
                # Busybox ifconfig: use alias interface notation
                f"ifconfig eth0:{next_num} {ip} netmask {netmask} up 2>/dev/null || ifconfig eth0 {ip} netmask {netmask} 2>/dev/null || true",
            ]
            # Add route for the subnet
            subnet = ".".join(ip.split(".")[:3]) + ".0"
            cmds.append(f"route add -net {subnet} netmask {netmask} eth0 2>/dev/null || ip route add {subnet}/{24 if netmask=='255.255.255.0' else '16'} dev eth0 2>/dev/null || true")
            for cmd in cmds:
                try: await self._ssh_execute(cmd)
                except: pass

            return ActionResult(action="add_alias", status=ActionStatus.SUCCESS,
                               message=f"Added alias {ip}/{netmask} on eth0")
        except Exception as e:
            return ActionResult(action="add_alias", status=ActionStatus.FAILED, error=str(e))

    async def remove_alias(self, ip: str) -> ActionResult:
        start = time.time()
        try:
            cfg = await self._ssh_execute("cat /tmp/system.cfg 2>/dev/null")
            for line in cfg.split("\n"):
                if f".ip={ip}" in line and "alias" in line:
                    pattern = line.split(".ip=")[0]
                    cmds = [
                        f"sed -i '/^{pattern}\\./d' /tmp/system.cfg",
                        f"ifconfig eth0 {ip} down 2>/dev/null",
                        f"cfgmtd -w -p /etc/ 2>/dev/null || true",
                    ]
                    for cmd in cmds:
                        try: await self._ssh_execute(cmd)
                        except: pass
                    return ActionResult(action="remove_alias", status=ActionStatus.SUCCESS,
                                       message=f"Removed alias {ip}")
            return ActionResult(action="remove_alias", status=ActionStatus.SUCCESS,
                               message=f"Alias {ip} not found")
        except Exception as e:
            return ActionResult(action="remove_alias", status=ActionStatus.FAILED, error=str(e))

    async def probe_subnets(self, aliases: list[str]) -> list[str]:
        """Lightweight probe: ping .1 and .254 on each alias subnet to populate ARP."""
        targets = set()
        for ip in aliases:
            parts = ip.split(".")
            if len(parts) == 4:
                base = f"{parts[0]}.{parts[1]}.{parts[2]}"
                targets.add(f"{base}.1")
                targets.add(f"{base}.254")

        for addr in sorted(targets):
            try:
                await self._ssh_execute(f"ping -c 1 -W 1 {addr} 2>/dev/null || true")
            except Exception:
                pass

        import asyncio
        await asyncio.sleep(0.5)
        return list(targets)

    async def get_running_state(self) -> RouterState:
        try:
            info = await self._ssh_execute("mca-status")
            state = RouterState(is_online=True)
            for line in info.split("\n"):
                if "dhcp" in line.lower():
                    state.dhcp_enabled = "enabled" in line.lower() or "running" in line.lower()

            iface = await self._ssh_execute("ifconfig ath0 2>/dev/null || ifconfig wlan0 2>/dev/null || echo ''")
            state.wifi_enabled = "UP" in iface

            try:
                ssid_line = await self._ssh_execute("grep 'radio.1.ssid\\|wlan.ssid' /tmp/system.cfg 2>/dev/null || echo ''")
                if ssid_line.strip():
                    ssid_val = ssid_line.split("=", 1)[-1].strip()
                    state.ssids = [{"ssid": ssid_val, "band": "2.4ghz"}]
            except Exception:
                pass

            return state
        except Exception:
            return RouterState(is_online=False)

    async def apply_config_commands(self, commands: list[str]) -> ActionResult:
        start = time.time()
        output = []
        try:
            for cmd in commands:
                out = await self._ssh_execute(cmd)
                output.append(f"$ {cmd}\n{out}")
            await self._ssh_execute("save")
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
            cmds = [
                f"sed -i 's/radio\\.1\\.ssid=.*/radio.1.ssid={config.ssid}/' /tmp/system.cfg",
                f"sed -i 's/wlan\\.ssid=.*/wlan.ssid={config.ssid}/' /tmp/system.cfg",
                f"sed -i 's/radio\\.1\\.auth=.*/radio.1.auth=psk2/' /tmp/system.cfg",
                f"sed -i 's/wpa\\.passphrase=.*/wpa.passphrase={config.password}/' /tmp/system.cfg",
            ]
            output = []
            for cmd in cmds:
                try:
                    out = await self._ssh_execute(cmd)
                    output.append(f"$ {cmd}\n{out}")
                except Exception:
                    pass
            await self._ssh_execute("save && /usr/etc/rc.d/rc.softrestart restart")
            elapsed = (time.time() - start) * 1000
            return ActionResult(
                action="set_wifi",
                status=ActionStatus.SUCCESS,
                output="\n".join(output),
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
            import base64
            import crypt
            import os
            salt = crypt.mksalt(crypt.METHOD_SHA512)
            hashed = crypt.crypt(config.password, salt)
            escaped = hashed.replace("/", "\\/")
            cmds = [
                f"sed -i 's/users\\.1\\.password=.*/users.1.password={escaped}/' /tmp/system.cfg",
                f"sed -i 's/users\\.1\\.name=.*/users.1.name={config.username}/' /tmp/system.cfg",
            ]
            for cmd in cmds:
                try:
                    await self._ssh_execute(cmd)
                except Exception:
                    pass
            await self._ssh_execute("save")
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
            if config.enabled:
                cmds = [
                    "sed -i 's/dhcpserver\\.status=.*/dhcpserver.status=enabled/' /tmp/system.cfg",
                ]
            else:
                cmds = [
                    "sed -i 's/dhcpserver\\.status=.*/dhcpserver.status=disabled/' /tmp/system.cfg",
                ]
            for cmd in cmds:
                try:
                    await self._ssh_execute(cmd)
                except Exception:
                    pass
            await self._ssh_execute("save && /usr/etc/rc.d/rc.softrestart restart")
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
            if enabled:
                cmds = [
                    "sed -i 's/netmode=.*/netmode=bridge/' /tmp/system.cfg",
                ]
            else:
                cmds = [
                    "sed -i 's/netmode=.*/netmode=router/' /tmp/system.cfg",
                ]
            for cmd in cmds:
                try:
                    await self._ssh_execute(cmd)
                except Exception:
                    pass
            await self._ssh_execute("save && /usr/etc/rc.d/rc.softrestart restart")
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
            await self._ssh_execute("reboot")
            return ActionResult(action="reboot", status=ActionStatus.SUCCESS, message="Rebooting")
        except Exception:
            return ActionResult(action="reboot", status=ActionStatus.SUCCESS, message="Reboot command sent (connection lost)")

    async def factory_reset(self) -> ActionResult:
        try:
            await self._ssh_execute("mca-cli-op set-default && reboot")
            return ActionResult(action="factory_reset", status=ActionStatus.SUCCESS, message="Factory reset initiated")
        except Exception:
            return ActionResult(action="factory_reset", status=ActionStatus.SUCCESS, message="Reset command sent (connection lost)")

    async def firmware_upgrade(self, image_path: str) -> ActionResult:
        """Upload a firmware image over SFTP and trigger the AirOS sysupgrade.

        image_path must be a local .bin file on the machine running the backend.
        """
        start = time.time()
        try:
            if not self._ssh_client:
                return ActionResult(action="firmware_upgrade", status=ActionStatus.FAILED, error="Not connected")
            if not os.path.isfile(image_path):
                return ActionResult(action="firmware_upgrade", status=ActionStatus.FAILED, error=f"Image not found: {image_path}")
            if not image_path.lower().endswith(".bin"):
                return ActionResult(action="firmware_upgrade", status=ActionStatus.FAILED, error="Firmware image must be a .bin file")

            remote = "/tmp/rcfirmware.bin"
            import asyncio

            def _upload() -> str:
                sftp = self._ssh_client.open_sftp()
                try:
                    sftp.put(image_path, remote)
                finally:
                    sftp.close()
                return "uploaded"

            await asyncio.get_event_loop().run_in_executor(None, _upload)

            # Verify size and trigger upgrade
            out = await self._ssh_execute(f"ls -l {remote} 2>/dev/null | awk '{{print $5}}'")
            if not out or out.strip() == "":
                return ActionResult(action="firmware_upgrade", status=ActionStatus.FAILED, error="Upload verification failed")

            await self._ssh_execute(f"mca-sysupgrade {remote} 2>&1 || syswrapper.sh upgrade {remote} 2>&1 || echo UPGRADE_TRIGGERED")
            elapsed = (time.time() - start) * 1000
            return ActionResult(
                action="firmware_upgrade",
                status=ActionStatus.SUCCESS,
                message="Firmware uploaded; upgrade triggered (device will reboot)",
                data={"image": os.path.basename(image_path), "bytes": out.strip()},
                duration_ms=elapsed,
            )
        except Exception as e:
            return ActionResult(action="firmware_upgrade", status=ActionStatus.FAILED, error=str(e))

    async def set_wifi_state(self, enabled: bool) -> ActionResult:
        try:
            state = "enabled" if enabled else "disabled"
            await self._ssh_execute(f"sed -i 's/radio\\.1\\.status=.*/radio.1.status={state}/' /tmp/system.cfg")
            await self._ssh_execute("save && /usr/etc/rc.d/rc.softrestart restart")
            return ActionResult(action="set_wifi_state", status=ActionStatus.SUCCESS, message=f"WiFi {'enabled' if enabled else 'disabled'}")
        except Exception as e:
            return ActionResult(action="set_wifi_state", status=ActionStatus.FAILED, error=str(e))

    async def get_connected_clients(self) -> ActionResult:
        try:
            out = await self._ssh_execute("mca-dump | grep sta")
            clients = [line.strip() for line in out.split("\n") if line.strip()]
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
            return ActionResult(
                action="custom_command",
                status=ActionStatus.SUCCESS,
                output=out,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return ActionResult(action="custom_command", status=ActionStatus.FAILED, error=str(e))
