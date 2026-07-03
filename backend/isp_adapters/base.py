from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class DHCPISPConfig:
    enabled: bool = False
    server_ip: str = ""
    dns_servers: list[str] = field(default_factory=list)
    ntp_servers: list[str] = field(default_factory=list)
    domain: str = ""


@dataclass
class WANISPConfig:
    vlan_id: int | None = None
    pppoe_enabled: bool = False
    pppoe_username_format: str = ""
    bridge_mode: bool = True


@dataclass
class DeviceUploadPayload:
    device_id: str
    site_id: str | None
    mac_address: str
    ip_address: str
    brand: str
    model: str
    ssid: str
    admin_username: str
    firmware_version: str
    wan_ip: str | None = None
    custom_fields: dict = field(default_factory=dict)


class ISPAdapter(ABC):

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def get_dhcp_config(self) -> DHCPISPConfig: ...

    @abstractmethod
    async def get_wan_config(self) -> WANISPConfig: ...

    @abstractmethod
    async def upload_device_info(self, payload: DeviceUploadPayload) -> bool: ...

    @abstractmethod
    async def upload_site_info(self, site_data: dict) -> bool: ...

    @abstractmethod
    async def test_connection(self) -> bool: ...

    @abstractmethod
    async def lookup_customer(self, identifier: str) -> dict | None: ...
