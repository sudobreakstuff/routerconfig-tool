from __future__ import annotations

import httpx

from isp_adapters.base import ISPAdapter, DHCPISPConfig, WANISPConfig, DeviceUploadPayload


class JennyInternetAdapter(ISPAdapter):

    def __init__(self, api_base_url: str = "", api_key: str = ""):
        self.api_base_url = api_base_url or "https://api.jennyinternet.co.za/v1"
        self.api_key = api_key

    @property
    def name(self) -> str:
        return "jenny_internet"

    async def get_dhcp_config(self) -> DHCPISPConfig:
        return DHCPISPConfig(
            enabled=False,
            server_ip="",
            dns_servers=["8.8.8.8", "1.1.1.1"],
            ntp_servers=["pool.ntp.org"],
            domain="jennyinternet.local",
        )

    async def get_wan_config(self) -> WANISPConfig:
        return WANISPConfig(
            vlan_id=None,
            pppoe_enabled=False,
            bridge_mode=True,
        )

    async def upload_device_info(self, payload: DeviceUploadPayload) -> bool:
        try:
            data = {
                "device_id": payload.device_id,
                "site_id": payload.site_id,
                "mac_address": payload.mac_address,
                "ip_address": payload.ip_address,
                "brand": payload.brand,
                "model": payload.model,
                "ssid": payload.ssid,
                "admin_username": payload.admin_username,
                "firmware_version": payload.firmware_version,
                "wan_ip": payload.wan_ip,
                **payload.custom_fields,
            }
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.api_base_url}/devices",
                    json=data,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                resp.raise_for_status()
                return True
        except Exception:
            return False

    async def upload_site_info(self, site_data: dict) -> bool:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.api_base_url}/sites",
                    json=site_data,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                resp.raise_for_status()
                return True
        except Exception:
            return False

    async def test_connection(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{self.api_base_url}/health",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return resp.status_code == 200
        except Exception:
            return False

    async def lookup_customer(self, identifier: str) -> dict | None:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{self.api_base_url}/customers/lookup",
                    params={"q": identifier},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                if resp.status_code == 200:
                    return resp.json()
                return None
        except Exception:
            return None
