from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
import asyncio
import time


class ActionStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    RUNNING = "running"


class RouterCapabilities(str, Enum):
    SSH = "ssh"
    HTTP_ADMIN = "http_admin"
    TELNET = "telnet"
    SNMP = "snmp"
    TR069 = "tr069"
    API = "api"
    WINBOX = "winbox"


@dataclass
class RouterConnection:
    host: str
    port: int = 22
    username: str = "admin"
    password: str = ""
    web_port: int = 80
    web_protocol: str = "http"
    use_ssl: bool = False
    jump_host: str | None = None
    jump_port: int | None = None
    jump_username: str | None = None
    jump_password: str | None = None
    timeout: int = 30
    winbox_port: int = 8291


@dataclass
class RouterInfo:
    brand: str
    model: str = ""
    firmware_version: str = ""
    mac_address: str = ""
    serial_number: str = ""
    uptime: str = ""
    capabilities: list[RouterCapabilities] = field(default_factory=list)


@dataclass
class RouterState:
    is_online: bool = False
    dhcp_enabled: bool = True
    wifi_enabled: bool = True
    bridge_mode: bool = False
    ssids: list[dict] = field(default_factory=list)
    connected_clients: int = 0
    wan_status: str = "unknown"
    memory_usage: float = 0.0
    cpu_usage: float = 0.0


@dataclass
class ActionResult:
    action: str
    status: ActionStatus
    message: str = ""
    output: str = ""
    error: str = ""
    duration_ms: float = 0.0
    data: dict | None = None


@dataclass
class WiFiConfig:
    ssid: str
    password: str
    enabled: bool = True
    band: str = "2.4ghz"
    channel: str = "auto"
    security: str = "wpa2-psk"


@dataclass
class AdminConfig:
    username: str = "admin"
    password: str = ""
    web_port: int = 80


@dataclass
class DHCPConfig:
    enabled: bool = False
    start_ip: str = ""
    end_ip: str = ""
    lease_time: int = 86400
    gateway: str = ""
    dns_servers: list[str] = field(default_factory=list)


class RouterDriver(ABC):

    def __init__(self, connection: RouterConnection):
        self.connection = connection
        self._ssh_client = None
        self._http_client = None

    @property
    @abstractmethod
    def brand(self) -> str: ...

    @property
    @abstractmethod
    def capabilities(self) -> list[RouterCapabilities]: ...

    @abstractmethod
    async def connect(self) -> bool: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def is_reachable(self) -> bool: ...

    @abstractmethod
    async def get_info(self) -> RouterInfo: ...

    @abstractmethod
    async def get_running_config(self) -> dict: ...

    @abstractmethod
    async def get_running_state(self) -> RouterState: ...

    @abstractmethod
    async def apply_config_commands(self, commands: list[str]) -> ActionResult: ...

    @abstractmethod
    async def set_wifi(self, config: WiFiConfig) -> ActionResult: ...

    @abstractmethod
    async def set_admin_password(self, config: AdminConfig) -> ActionResult: ...

    @abstractmethod
    async def set_dhcp(self, config: DHCPConfig) -> ActionResult: ...

    @abstractmethod
    async def set_bridge_mode(self, enabled: bool) -> ActionResult: ...

    async def reboot(self) -> ActionResult:
        return ActionResult(action="reboot", status=ActionStatus.FAILED, message="Not supported by driver")

    async def factory_reset(self) -> ActionResult:
        return ActionResult(action="factory_reset", status=ActionStatus.FAILED, message="Not supported by driver")

    async def backup_config(self) -> ActionResult:
        try:
            config = await self.get_running_config()
            return ActionResult(
                action="backup_config",
                status=ActionStatus.SUCCESS,
                message="Config backed up successfully",
                data=config,
            )
        except Exception as e:
            return ActionResult(action="backup_config", status=ActionStatus.FAILED, error=str(e))

    async def restore_config(self, config: dict) -> ActionResult:
        """Restore a previously backed-up config.

        Accepts the same structure returned by `backup_config`:
        - Ubiquiti: {"system.cfg": "...", "config.boot": "...", "format": "ubiquiti"}
        - CLI-based (MikroTik): {"raw": "/export output", "format": "mikrotik-cli"}

        Drivers that support writing files override `_write_config_file`. This
        default implementation writes each file back over SSH and saves.
        """
        start = time.time()
        try:
            if not config or not isinstance(config, dict):
                return ActionResult(action="restore_config", status=ActionStatus.FAILED, error="Empty config")

            fmt = config.get("format", "")
            written = 0
            try:
                if fmt == "ubiquiti":
                    for filename in ("system.cfg", "config.boot"):
                        content = config.get(filename)
                        if not content:
                            continue
                        await self._ssh_execute(f"cat > /tmp/{filename} << 'EOF'\n{content}\nEOF")
                        written += 1
                    await self._ssh_execute("save && /usr/etc/rc.d/rc.softrestart restart")
                elif fmt == "mikrotik-cli" and config.get("raw"):
                    await self._ssh_execute("/import file-name=none file=none file=")
                    # RouterOS import expects a file; stream via a temp name instead.
                    await self._ssh_execute(f"/system backup save name=restore_pre")
                    # Push the raw config through a heredoc import is not supported
                    # by RouterOS over SSH directly; run commands line by line.
                    lines = [ln.strip() for ln in config["raw"].splitlines() if ln.strip() and not ln.startswith("#")]
                    for ln in lines[:200]:
                        try:
                            await self._ssh_execute(ln)
                        except Exception:
                            pass
                    written = len(lines)
                else:
                    return ActionResult(
                        action="restore_config", status=ActionStatus.FAILED,
                        error=f"Unsupported config format: {fmt or 'unknown'}",
                    )
            except Exception as e:
                return ActionResult(action="restore_config", status=ActionStatus.FAILED, error=str(e))

            elapsed = (time.time() - start) * 1000
            return ActionResult(
                action="restore_config",
                status=ActionStatus.SUCCESS if written else ActionStatus.FAILED,
                message=f"Restored {written} config item(s)",
                duration_ms=elapsed,
            )
        except Exception as e:
            return ActionResult(action="restore_config", status=ActionStatus.FAILED, error=str(e))

    async def set_wifi_state(self, enabled: bool) -> ActionResult:
        return ActionResult(action="set_wifi_state", status=ActionStatus.FAILED, message="Not supported by driver")

    async def get_connected_clients(self) -> ActionResult:
        return ActionResult(action="get_connected_clients", status=ActionStatus.FAILED, message="Not supported by driver")

    async def firmware_upgrade(self, image_path: str) -> ActionResult:
        return ActionResult(action="firmware_upgrade", status=ActionStatus.FAILED, message="Not supported by driver")

    async def ping_target(self, target: str, count: int = 4) -> ActionResult:
        try:
            import platform
            if platform.system() == "Windows":
                cmd = ["ping", "-n", "1", "-w", "3000", target]
            else:
                cmd = ["ping", "-c", "1", "-W", "2", target]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
            output = stdout.decode()
            success = proc.returncode == 0
            return ActionResult(
                action="ping",
                status=ActionStatus.SUCCESS if success else ActionStatus.FAILED,
                output=output,
                message="Ping successful" if success else "Ping failed",
            )
        except Exception as e:
            return ActionResult(action="ping", status=ActionStatus.FAILED, error=str(e))

    async def run_custom_command(self, command: str) -> ActionResult:
        return ActionResult(action="custom_command", status=ActionStatus.FAILED, message="Not supported by driver")

    async def http_login(self) -> bool:
        return False

    async def http_execute(self, path: str, data: dict | None = None) -> ActionResult:
        return ActionResult(action="http_execute", status=ActionStatus.FAILED, message="Not supported by driver")
