from __future__ import annotations

import json
import os

from isp_adapters.base import ISPAdapter, DHCPISPConfig, WANISPConfig, DeviceUploadPayload


class CustomAdapter(ISPAdapter):

    def __init__(self, config_path: str = "", **kwargs):
        self.config_path = config_path or os.path.expanduser("~/.routerconfig/isp_custom.json")
        self.config: dict = {}
        self._load_config()

        for key, val in kwargs.items():
            setattr(self, key, val)

    def _load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path) as f:
                    self.config = json.load(f)
            except Exception:
                self.config = {}

    @property
    def name(self) -> str:
        return "custom"

    async def get_dhcp_config(self) -> DHCPISPConfig:
        dhcp = self.config.get("dhcp", {})
        return DHCPISPConfig(
            enabled=dhcp.get("enabled", False),
            server_ip=dhcp.get("server_ip", ""),
            dns_servers=dhcp.get("dns_servers", ["8.8.8.8"]),
            ntp_servers=dhcp.get("ntp_servers", ["pool.ntp.org"]),
            domain=dhcp.get("domain", ""),
        )

    async def get_wan_config(self) -> WANISPConfig:
        wan = self.config.get("wan", {})
        return WANISPConfig(
            vlan_id=wan.get("vlan_id"),
            pppoe_enabled=wan.get("pppoe_enabled", False),
            pppoe_username_format=wan.get("pppoe_username_format", ""),
            bridge_mode=wan.get("bridge_mode", True),
        )

    async def upload_device_info(self, payload: DeviceUploadPayload) -> bool:
        endpoint = self.config.get("upload_endpoint", "")
        api_key = self.config.get("api_key", "")
        if not endpoint:
            return False
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    endpoint,
                    json={
                        "device_id": payload.device_id,
                        "mac_address": payload.mac_address,
                        "ip_address": payload.ip_address,
                        "brand": payload.brand,
                        "model": payload.model,
                        "ssid": payload.ssid,
                        **payload.custom_fields,
                    },
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                return resp.status_code < 400
        except Exception:
            return False

    async def upload_site_info(self, site_data: dict) -> bool:
        endpoint = self.config.get("upload_endpoint_sites", self.config.get("upload_endpoint", ""))
        api_key = self.config.get("api_key", "")
        if not endpoint:
            return False
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    endpoint,
                    json=site_data,
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                return resp.status_code < 400
        except Exception:
            return False

    async def test_connection(self) -> bool:
        return True

    async def lookup_customer(self, identifier: str) -> dict | None:
        return None

    @classmethod
    def from_json_file(cls, path: str) -> CustomAdapter:
        return cls(config_path=path)

    def update_config(self, updates: dict) -> None:
        self.config.update(updates)
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self.config, f, indent=2)
