from __future__ import annotations

import asyncio
import time
from datetime import datetime

from core.drivers.base import RouterConnection, WiFiConfig, AdminConfig, DHCPConfig
from core.drivers.factory import DriverFactory
from core.password_gen import generate_wifi_password, generate_admin_password, generate_ssid
from core.discovery import ping_host, _probe_ports


async def test_device_connection(ip: str, username: str = "admin", password: str = "admin",
                                  ssh_port: int = 22, web_port: int = 80) -> dict:
    """Test if a device is reachable and accessible."""
    result = {"reachable": False, "auth": False, "brand": "unknown", "model": "", "ports": []}

    # Ping is a soft signal - many routers block ICMP while serving HTTP/SSH.
    ping_ok = await ping_host(ip)
    result["reachable"] = ping_ok

    # Port scan is the authoritative reachability check (TCP-based, works even
    # when ICMP is blocked).
    ports = await _probe_ports(ip)
    result["ports"] = ports
    if not result["reachable"]:
        result["reachable"] = bool(ports)

    if not result["reachable"]:
        return result

    # Try HTTP first - more routers have web admin than SSH
    if 80 in ports or 443 in ports:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=8, verify=False) as client:
                resp = await client.get(f"http://{ip}:{web_port}/")
                text = resp.text[:5000].lower()
                if "mikrotik" in text or "routeros" in text:
                    result["brand"] = "mikrotik"
                elif "tplink" in text or "tp-link" in text:
                    result["brand"] = "tplink"
                elif "ubiquiti" in text or "unifi" in text:
                    result["brand"] = "ubiquiti"
                result["auth"] = True  # HTTP responded, we can at least reach it
        except Exception:
            pass

    # Try SSH
    if (22 in ports or 8291 in ports) and not result["auth"]:
        try:
            from core.ssh_compat import create_ssh_client
            client = create_ssh_client()
            client.connect(ip, port=ssh_port, username=username, password=password,
                          timeout=8, banner_timeout=8, auth_timeout=8)
            result["auth"] = True
            stdin, stdout, stderr = client.exec_command("cat /etc/version 2>/dev/null; cat /tmp/system.cfg 2>/dev/null | head -5; uname -a 2>/dev/null", timeout=5)
            out = stdout.read().decode(errors="replace").lower()
            if "mikrotik" in out or "routeros" in out:
                result["brand"] = "mikrotik"
            elif "ubiquiti" in out:
                result["brand"] = "ubiquiti"
            client.close()
        except Exception:
            pass

    return result
