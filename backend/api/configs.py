from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
import json
import re as regex

from database.connection import get_session
from services.config_service import ConfigService
from services.remote_service import RemoteService
from core.connection_test import test_device_connection
from core.drivers.base import RouterConnection
from core.drivers.factory import DriverFactory

router = APIRouter()


@router.post("/read-config")
async def read_device_config(data: dict):
    """Read current config from a device without making changes."""
    ip = data.get("host", data.get("ip_address", ""))
    username = data.get("username", "admin")
    password = data.get("password", "")
    brand = data.get("brand", "generic")
    ssh_port = data.get("ssh_port", 22)
    web_port = data.get("web_port", 80)

    if not ip:
        raise HTTPException(status_code=400, detail="host/ip_address is required")

    conn = RouterConnection(
        host=ip, port=ssh_port, username=username, password=password, web_port=web_port,
    )
    driver = DriverFactory.create(brand, conn)

    connected = await driver.connect()
    if not connected:
        raise HTTPException(status_code=400, detail="Cannot connect to device")

    info = await driver.get_info()
    config = await driver.get_running_config()
    state = await driver.get_running_state()

    await driver.disconnect()

    # Discover downstream devices by actually scanning from the device
    downstream = []
    try:
        if hasattr(driver, "discover_downstream_devices"):
            downstream = await driver.discover_downstream_devices()
    except Exception:
        pass

    # If no downstream discovery from driver, fall back to generic ARP scan
    if not downstream:
        try:
            arp_out = await driver._ssh_execute("arp -a 2>/dev/null; ip neigh show 2>/dev/null")
            for line in arp_out.split("\n"):
                ips = regex.findall(r'(\d+\.\d+\.\d+\.\d+)', line)
                macs = regex.findall(r'([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', line)
                if ips:
                    downstream.append({
                        "ip": ips[0],
                        "mac": macs[0] if macs else "",
                        "source": "arp-scan",
                    })
        except Exception:
            pass

    await driver.disconnect()

    # Extract IPs from config text (supplemental - includes aliases for AC equipment)
    config_ips = []
    if config and isinstance(config, dict):
        config_text = json.dumps(config) if not isinstance(config.get("raw"), str) else config.get("raw", "")
        found_ips = set(d["ip"] for d in downstream if d.get("ip"))
        # Look for alias IPs specifically (critical for airOS AC equipment)
        for alias in regex.findall(r'alias\.\d+\.ip=(\d+\.\d+\.\d+\.\d+)', config_text):
            if alias not in found_ips and not alias.startswith("127.") and not alias.startswith("0.") and not alias.startswith("169.254"):
                found_ips.add(alias)
                config_ips.append(alias)
        for ip in regex.findall(r'(\d+\.\d+\.\d+\.\d+)', config_text):
            ip = ip.strip()
            if ip not in found_ips and not ip.startswith("127.") and not ip.startswith("0.") and not ip.startswith("169.254") and not ip.startswith("255."):
                found_ips.add(ip)
                config_ips.append(ip)

    return {
        "brand": info.brand,
        "model": info.model,
        "firmware_version": info.firmware_version,
        "mac_address": info.mac_address,
        "uptime": info.uptime,
        "dhcp_enabled": state.dhcp_enabled,
        "wifi_enabled": state.wifi_enabled,
        "bridge_mode": state.bridge_mode,
        "ssids": state.ssids,
        "connected_clients": state.connected_clients,
        "running_config": config,
        "config_ips": config_ips[:20],
        "downstream_devices": [{"ip": d["ip"], "mac": d.get("mac", ""), "source": d.get("source", "")} for d in downstream[:30]],
    }


@router.post("/setup")
async def setup_device(
    data: dict,
    session: AsyncSession = Depends(get_session),
):
    result = await ConfigService.setup_device(session, data)
    return {
        "success": result.status.value == "success",
        "device_id": result.task.device_id,
        "router_info": {
            "brand": result.router_info.brand if result.router_info else None,
            "model": result.router_info.model if result.router_info else None,
            "firmware": result.router_info.firmware_version if result.router_info else None,
        },
        "errors": result.errors,
        "output_log": result.output_log,
        "duration_ms": result.duration_ms,
        "config_applied": result.config_applied,
    }


@router.post("/setup/bulk")
async def setup_bulk(
    data: dict,
    session: AsyncSession = Depends(get_session),
):
    devices_data = data.get("devices", [])
    max_concurrent = data.get("max_concurrent", 5)
    if not devices_data:
        raise HTTPException(status_code=400, detail="No devices provided")

    results = await ConfigService.setup_bulk(
        session, devices_data, max_concurrent=max_concurrent,
    )
    return {
        "total": len(results),
        "successful": sum(1 for r in results if r.status.value == "success"),
        "failed": sum(1 for r in results if r.status.value == "failed"),
        "results": [
            {
                "ip": r.task.device_ip,
                "device_id": r.task.device_id,
                "success": r.status.value == "success",
                "brand": r.router_info.brand if r.router_info else None,
                "model": r.router_info.model if r.router_info else None,
                "errors": r.errors,
                "duration_ms": r.duration_ms,
            }
            for r in results
        ],
    }


@router.post("/action")
async def run_action(
    data: dict,
    session: AsyncSession = Depends(get_session),
):
    device_id = data.get("device_id")
    action = data.get("action")
    connection = data.get("connection")
    params = data.get("params")

    if not device_id or not action or not connection:
        raise HTTPException(status_code=400, detail="device_id, action, and connection are required")

    result = await ConfigService.run_action(device_id, connection, action, params)
    return result


@router.post("/test-connection")
async def test_connection(
    data: dict,
):
    ip = data.get("host", data.get("ip_address", ""))
    username = data.get("username", "admin")
    password = data.get("password", data.get("current_password", "admin"))
    ssh_port = data.get("ssh_port", 22)
    web_port = data.get("web_port", 80)

    result = await test_device_connection(
        ip=ip,
        username=username,
        password=password,
        ssh_port=ssh_port,
        web_port=web_port,
    )
    return {
        "success": result["auth"] and result["reachable"],
        "reachable": result["reachable"],
        "auth": result["auth"],
        "brand": result["brand"],
        "model": result.get("model", ""),
        "ports": result.get("ports", []),
    }
