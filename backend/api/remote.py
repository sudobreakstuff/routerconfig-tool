from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

import asyncio

from database.connection import get_session
from services.remote_service import RemoteService
from services.device_service import DeviceService
from models.connection_profile import ConnectionProfile
from models.baseline import Baseline
from core.encryption import encrypt, decrypt
from core.drivers.base import RouterConnection
from core.drivers.factory import DriverFactory
from core.drivers.base import ActionResult, ActionStatus

router = APIRouter()


@router.get("/connection/{device_id}")
async def get_connection_info(
    device_id: str,
    session: AsyncSession = Depends(get_session),
):
    device = await DeviceService.get_by_id(session, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    connection = await RemoteService.get_connection_profile(device)

    result = await session.execute(
        select(ConnectionProfile)
        .where(ConnectionProfile.device_id == device_id)
        .order_by(ConnectionProfile.last_success.desc())
        .limit(5)
    )
    profiles = result.scalars().all()

    return {
        "device_id": device_id,
        "current": connection,
        "saved_profiles": [
            {
                "id": p.id,
                "label": p.label,
                "ssh_host": p.ssh_host,
                "ssh_port": p.ssh_port,
                "web_admin_url": p.web_admin_url,
                "web_admin_port": p.web_admin_port,
                "jump_host": p.jump_host,
                "last_success": p.last_success.isoformat() if p.last_success else None,
                "use_count": p.use_count,
                "is_favorite": p.is_favorite,
            }
            for p in profiles
        ],
    }


@router.post("/open-tunnel")
async def open_ssh_tunnel(data: dict):
    """Check reachability and provide SSH tunnel command."""
    from core.ssh_compat import create_ssh_client

    jump_ip = data.get("jump_host", "")
    jump_user = data.get("jump_username", "admin")
    jump_pass = data.get("jump_password", "")
    jump_port = data.get("jump_port", 22)
    target_ip = data.get("target_ip", "")
    target_port = data.get("target_port", 80)

    if not jump_ip or not target_ip:
        raise HTTPException(status_code=400, detail="jump_host and target_ip are required")

    # Check if target is reachable from the jump host
    reachable = False
    route_info = ""
    try:
        ssh = create_ssh_client()
        ssh.connect(jump_ip, port=jump_port, username=jump_user, password=jump_pass, timeout=10, banner_timeout=8)

        # Try multiple route add formats (busybox-compatible, no 'dev' keyword)
        subnet = ".".join(target_ip.split(".")[:3]) + ".0"
        for route_cmd in [
            f"route add -net {subnet} netmask 255.255.255.0 eth0 2>&1",
            f"route add -net {subnet}/24 eth0 2>&1",
            f"ip route add {subnet}/24 dev eth0 2>&1",
            f"route add {subnet} netmask 255.255.255.0 eth0 2>&1",
        ]:
            try:
                _s, _o, _e = ssh.exec_command(route_cmd, timeout=5)
            except: pass

        import time as _time
        _time.sleep(0.5)

        # Show routes and interfaces for debugging
        try:
            _s, _o, _e = ssh.exec_command("route -n 2>&1; echo '---IF---'; ifconfig 2>&1 | grep -E 'Link|inet|eth|br' | head -10", timeout=5)
            route_info = _o.read().decode(errors="replace")[:500]
        except: pass

        # Try pinging the target from the jump host
        _s, _o, _e = ssh.exec_command(f"ping -c 2 -W 2 {target_ip} 2>&1", timeout=10)
        out = _o.read().decode(errors="replace")
        reachable = "bytes from" in out.lower() or "1 received" in out

        ssh.close()
    except Exception:
        pass

    return {
        "reachable": reachable,
        "ssh_command": f"ssh -L 8888:{target_ip}:{target_port} {jump_user}@{jump_ip} -p {jump_port}",
        "target": f"{target_ip}:{target_port}",
        "route_info": route_info,
        "help": "Run this command in your terminal, then open http://localhost:8888" if reachable
                else f"Target unreachable from jump host.\n\nRouting table:\n{route_info}",
    }


@router.post("/manage-alias")
async def manage_alias(data: dict):
    """Add or remove IP aliases on a connected device.
    Required for reaching customer routers on different subnets (e.g., Jenny Internet uses 192.168.0.5)."""
    ip = data.get("host", data.get("ip_address", ""))
    username = data.get("username", "admin")
    password = data.get("password", "")
    brand = data.get("brand", "ubiquiti")
    action = data.get("action", "add")  # add, remove, list
    alias_ip = data.get("alias_ip", "")
    alias_netmask = data.get("alias_netmask", "255.255.255.0")

    if not ip:
        raise HTTPException(status_code=400, detail="host is required")

    conn = RouterConnection(host=ip, port=22, username=username, password=password)
    driver = DriverFactory.create(brand, conn)

    connected = await driver.connect()
    if not connected:
        raise HTTPException(status_code=400, detail="Cannot connect to device")

    try:
        if action == "list":
            if hasattr(driver, "list_aliases"):
                aliases = await driver.list_aliases()
            else:
                aliases = []
            return {"aliases": aliases}

        elif action == "add":
            if not alias_ip:
                raise HTTPException(status_code=400, detail="alias_ip is required")
            if hasattr(driver, "add_alias"):
                result = await driver.add_alias(alias_ip, alias_netmask)
            else:
                result = ActionResult(action="add_alias", status=ActionStatus.FAILED,
                                      error="Alias management not supported for this device")
            return {"success": result.status == ActionStatus.SUCCESS,
                    "message": result.message, "error": getattr(result, "error", "")}

        elif action == "remove":
            if not alias_ip:
                raise HTTPException(status_code=400, detail="alias_ip is required")
            if hasattr(driver, "remove_alias"):
                result = await driver.remove_alias(alias_ip)
            else:
                result = ActionResult(action="remove_alias", status=ActionStatus.FAILED,
                                      error="Alias management not supported")
            return {"success": result.status == ActionStatus.SUCCESS,
                    "message": result.message, "error": getattr(result, "error", "")}

        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {action}")
    finally:
        await driver.disconnect()


@router.post("/connection/{device_id}")
async def save_connection(
    device_id: str,
    data: dict,
    session: AsyncSession = Depends(get_session),
):
    profile = await RemoteService.save_connection_profile(session, device_id, data)
    return {
        "id": profile.id,
        "label": profile.label,
        "ssh_host": profile.ssh_host,
        "ssh_port": profile.ssh_port,
    }


@router.post("/connect/{device_id}")
async def connect_to_device(
    device_id: str,
    data: dict | None = None,
    session: AsyncSession = Depends(get_session),
):
    device = await DeviceService.get_by_id(session, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    connection_data = data or await RemoteService.get_connection_profile(device)
    result = await RemoteService.test_connection(connection_data)

    if result.get("success"):
        await DeviceService.update_online_status(session, device_id, True)
        result["device_name"] = device.name

    return result


@router.post("/baseline/{device_id}")
async def take_baseline(
    device_id: str,
    data: dict | None = None,
    session: AsyncSession = Depends(get_session),
):
    device = await DeviceService.get_by_id(session, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    connection_data = data or await RemoteService.get_connection_profile(device)

    from core.drivers.base import RouterConnection
    from core.drivers.factory import DriverFactory

    conn = RouterConnection(
        host=connection_data["host"],
        port=connection_data.get("ssh_port", 22),
        username=connection_data.get("username", "admin"),
        password=connection_data.get("password", ""),
        web_port=connection_data.get("web_port", 80),
    )
    driver = DriverFactory.create(
        connection_data.get("brand", device.brand.value if device.brand else "generic"),
        conn,
    )

    connected = await driver.connect()
    if not connected:
        raise HTTPException(status_code=400, detail="Cannot connect to device")

    config = await driver.get_running_config()
    state = await driver.get_running_state()
    await driver.disconnect()

    baseline = Baseline(
        device_id=device_id,
        label=data.get("label", "") if data else "",
        full_config=config,
        running_state={
            "dhcp_enabled": state.dhcp_enabled,
            "wifi_enabled": state.wifi_enabled,
            "bridge_mode": state.bridge_mode,
            "ssids": state.ssids,
            "is_online": True,
        },
        triggered_by=data.get("triggered_by", "manual") if data else "manual",
    )
    session.add(baseline)
    await session.commit()
    await session.refresh(baseline)

    return {
        "id": baseline.id,
        "device_id": device_id,
        "created_at": baseline.created_at.isoformat() if baseline.created_at else None,
    }


@router.get("/baselines/{device_id}")
async def get_baselines(
    device_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(Baseline)
        .where(Baseline.device_id == device_id)
        .order_by(Baseline.created_at.desc())
        .limit(10)
    )
    baselines = result.scalars().all()
    return [
        {
            "id": b.id,
            "label": b.label,
            "triggered_by": b.triggered_by,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        }
        for b in baselines
    ]


@router.post("/discover-downstream")
async def discover_downstream_devices(data: dict):
    """Scan the network from a connected device to find downstream routers/clients."""
    ip = data.get("host", data.get("ip_address", ""))
    username = data.get("username", "admin")
    password = data.get("password", "")
    brand = data.get("brand", "ubiquiti")
    ssh_port = data.get("ssh_port", 22)
    web_port = data.get("web_port", 80)

    if not ip:
        raise HTTPException(status_code=400, detail="host/ip_address is required")

    conn = RouterConnection(host=ip, port=ssh_port, username=username, password=password, web_port=web_port)
    driver = DriverFactory.create(brand, conn)

    connected = await driver.connect()
    if not connected:
        raise HTTPException(status_code=400, detail="Cannot connect to device")

    # If aliases are provided, use them for probing first
    probe_aliases = data.get("aliases", [])

    has_downstream = hasattr(driver, "discover_downstream_devices")
    if probe_aliases:
        devices = await driver.discover_downstream_devices(probe_aliases=probe_aliases) if has_downstream else []
    else:
        devices = await driver.discover_downstream_devices() if has_downstream else []

    if not devices and hasattr(driver, "_ssh_execute"):
        # Generic fallback - run ARP scan on the device
        try:
            arp_out = await driver._ssh_execute("arp -a 2>/dev/null; ip neigh show 2>/dev/null")
            for line in arp_out.split("\n"):
                ips = __import__("re").findall(r'(\d+\.\d+\.\d+\.\d+)', line)
                macs = __import__("re").findall(r'([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', line)
                if ips:
                    devices.append({"ip": ips[0], "mac": macs[0] if macs else "", "source": "arp"})
        except Exception:
            pass

    await driver.disconnect()

    # Build web admin URLs for discovered devices
    result = []
    for d in devices:
        result.append({
            "ip": d.get("ip", ""),
            "mac": d.get("mac", ""),
            "mac_vendor": d.get("mac_vendor", ""),
            "source": d.get("source", "arp"),
            "web_admin_url": f"http://{d['ip']}" if d.get("ip") else "",
            "ssh_command": f"ssh {username}@{d['ip']}" if d.get("ip") else "",
        })

    return {
        "host_device_ip": ip,
        "host_device_brand": brand,
        "discovered_count": len(result),
        "devices": result,
    }
