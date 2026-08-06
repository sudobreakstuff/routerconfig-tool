from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json
import re as regex
import asyncio

from database.connection import get_session
from services.config_service import ConfigService
from services.device_service import DeviceService
from services.remote_service import RemoteService
from core.connection_test import test_device_connection
from core.drivers.base import RouterConnection
from core.drivers.factory import DriverFactory
from core.encryption import decrypt
from models.isp_profile import ISPProfile
from isp_adapters.registry import ISPAdapterRegistry
from isp_adapters.base import DeviceUploadPayload

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


@router.post("/deploy")
async def deploy_device(
    data: dict,
    session: AsyncSession = Depends(get_session),
):
    """End-to-end CPE deployment for the Jenny workflow:
    read device -> apply config (setup) -> upload to ISP inventory.

    Requires the config keys used by /setup plus an optional profile_id (or the
    device's site must already be linked to an ISP profile).
    """
    device_id = data.get("device_id")

    if device_id:
        device = await DeviceService.get_by_id(session, device_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        # Merge stored device credentials into the payload so setup can run.
        base = {
            "ip_address": device.ip_address or "",
            "username": device.admin_username,
            "password": decrypt(device.admin_password_encrypted) if device.admin_password_encrypted else "",
            "brand": device.brand.value if device.brand else "generic",
            "ssh_port": device.ssh_port or 22,
            "web_port": device.web_port or 80,
        }
        data = {**base, **data}

    setup_result = await ConfigService.setup_device(session, data)
    setup_ok = setup_result.status.value == "success"

    upload_result = None
    if setup_ok:
        profile_id = data.get("profile_id")
        target_id = data.get("device_id")
        profile = None
        if profile_id:
            res = await session.execute(select(ISPProfile).where(ISPProfile.id == profile_id))
            profile = res.scalar_one_or_none()
        if not profile and target_id:
            dev = await DeviceService.get_by_id(session, target_id)
            if dev and dev.site_id:
                res = await session.execute(select(ISPProfile).where(ISPProfile.id == dev.site_id))
                profile = res.scalar_one_or_none()
        if profile:
            try:
                adapter = ISPAdapterRegistry.create(
                    profile.adapter_name,
                    api_base_url=profile.upload_endpoint or "",
                    api_key=decrypt(profile.upload_api_key_encrypted) if profile.upload_api_key_encrypted else "",
                )
                if adapter:
                    payload = DeviceUploadPayload(
                        device_id=target_id or "",
                        site_id=data.get("site_id"),
                        mac_address=data.get("mac_address", ""),
                        ip_address=data.get("ip_address", ""),
                        brand=data.get("brand", "unknown"),
                        model=data.get("model", "") or setup_result.router_info.model if setup_result.router_info else "",
                        ssid=data.get("wifi_ssid", ""),
                        admin_username=data.get("username", "admin"),
                        firmware_version=setup_result.router_info.firmware_version if setup_result.router_info else "",
                        custom_fields=data.get("custom_fields", {}),
                    )
                    upload_result = {"success": await adapter.upload_device_info(payload)}
                else:
                    upload_result = {"success": False, "error": "Unknown adapter"}
            except Exception as e:
                upload_result = {"success": False, "error": str(e)}

    return {
        "success": setup_ok,
        "device_id": setup_result.task.device_id,
        "setup": {
            "success": setup_ok,
            "errors": setup_result.errors,
            "output_log": setup_result.output_log,
            "duration_ms": setup_result.duration_ms,
            "config_applied": setup_result.config_applied,
            "router_info": {
                "brand": setup_result.router_info.brand if setup_result.router_info else None,
                "model": setup_result.router_info.model if setup_result.router_info else None,
                "firmware": setup_result.router_info.firmware_version if setup_result.router_info else None,
            },
        },
        "isp_upload": upload_result,
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

    try:
        result = await asyncio.wait_for(
            test_device_connection(
                ip=ip,
                username=username,
                password=password,
                ssh_port=ssh_port,
                web_port=web_port,
            ),
            timeout=30,
        )
    except Exception as e:
        return {
            "success": False,
            "reachable": False,
            "auth": False,
            "brand": "unknown",
            "model": "",
            "ports": [],
            "error": f"{type(e).__name__}: {e}",
        }
    return {
        "success": result["auth"] and result["reachable"],
        "reachable": result["reachable"],
        "auth": result["auth"],
        "brand": result["brand"],
        "model": result.get("model", ""),
        "ports": result.get("ports", []),
    }