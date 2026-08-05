from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_session
from services.config_service import ConfigService
from services.device_service import DeviceService
from services.remote_service import RemoteService
from core.connection_pool import pool
from core.discovery import ping_host
from core.tunnel_manager import close_tunnel, list_tunnels, open_tunnel
from core.drivers.factory import DriverFactory
from core.drivers.base import RouterConnection

router = APIRouter()

AVAILABLE_ACTIONS = [
    "reboot", "factory_reset", "backup_config", "restore_config", "firmware_upgrade", "get_connected_clients",
    "wifi_on", "wifi_off", "set_wifi", "set_admin_password", "set_dhcp", "run_command",
]


@router.get("/available")
async def list_actions():
    return [{"action": a, "label": a.replace("_", " ").title()} for a in AVAILABLE_ACTIONS]


@router.post("/execute")
async def execute_action(data: dict, session: AsyncSession = Depends(get_session)):
    device_id = data.get("device_id")
    action = data.get("action")
    params = data.get("params", {})
    connection = data.get("connection")

    if not device_id or not action:
        raise HTTPException(status_code=400, detail="device_id and action are required")

    if not connection:
        device = await DeviceService.get_by_id(session, device_id)
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        connection = await RemoteService.get_connection_profile(device)

    result = await ConfigService.run_action(device_id, connection, action, params)
    if action in ("reboot", "factory_reset") and result.get("success"):
        await DeviceService.update_online_status(session, device_id, False)
    return result


@router.post("/execute/bulk")
async def execute_bulk_action(data: dict, session: AsyncSession = Depends(get_session)):
    """Run a single action across multiple devices concurrently."""
    import asyncio

    device_ids = data.get("device_ids", [])
    action = data.get("action")
    params = data.get("params", {})
    max_concurrent = int(data.get("max_concurrent", 5))

    if not device_ids or not action:
        raise HTTPException(status_code=400, detail="device_ids and action are required")

    results = []
    for i in range(0, len(device_ids), max_concurrent):
        batch = device_ids[i:i + max_concurrent]
        pairs = []  # (device_id, task)
        for device_id in batch:
            device = await DeviceService.get_by_id(session, device_id)
            if not device:
                results.append({"device_id": device_id, "success": False, "error": "Device not found"})
                continue
            connection = await RemoteService.get_connection_profile(device)
            pairs.append((device_id, ConfigService.run_action(device_id, connection, action, params)))

        if not pairs:
            continue

        completed = await asyncio.gather(*[t for _, t in pairs], return_exceptions=True)
        for (device_id, _), res in zip(pairs, completed):
            if isinstance(res, Exception):
                results.append({"device_id": device_id, "success": False, "error": str(res)})
            else:
                results.append({"device_id": device_id, **res})
                if action in ("reboot", "factory_reset") and res.get("success"):
                    await DeviceService.update_online_status(session, device_id, False)

    return {"results": results, "count": len(results)}


# -- Persistent SSH command execution (reuses connection pool) --

@router.post("/cmd")
async def ssh_command(data: dict):
    """Execute an SSH command on a device using persistent connection pool."""
    host = data.get("host", "")
    username = data.get("username", "admin")
    password = data.get("password", "")
    port = data.get("port", data.get("ssh_port", 22))
    command = data.get("command", "")

    if not host or not command:
        raise HTTPException(status_code=400, detail="host and command are required")

    try:
        output = await pool.execute(host, username, password, command, port, timeout=15)
        return {"output": output, "error": ""}
    except Exception as e:
        return {"output": "", "error": str(e)}


@router.post("/connect")
async def connect_device(data: dict):
    """Open persistent SSH connection to a device."""
    host = data.get("host", "")
    username = data.get("username", "admin")
    password = data.get("password", "")
    port = data.get("port", data.get("ssh_port", 22))

    if not host:
        raise HTTPException(status_code=400, detail="host is required")

    try:
        ssh = pool.get(host, username, password, port)
        # Get device info to confirm it works
        stdin, stdout, stderr = ssh.exec_command("mca-status 2>/dev/null || cat /proc/version 2>/dev/null || uname -a", timeout=10)
        out = stdout.read().decode(errors="replace").strip()

        import re as _re
        model = _re.search(r'platform=([^,]+)', out)
        fw = _re.search(r'firmwareVersion=([^,]+)', out)
        mac = _re.search(r'deviceMac=([0-9a-fA-F:]+)', out)

        return {
            "connected": True,
            "host": host,
            "model": model.group(1) if model else "unknown",
            "firmware": fw.group(1) if fw else "unknown",
            "mac": mac.group(1) if mac else "",
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}


@router.post("/disconnect")
async def disconnect_device(data: dict):
    """Close persistent SSH connection to a device."""
    host = data.get("host", "")
    username = data.get("username", "admin")
    password = data.get("password", "")
    port = data.get("port", data.get("ssh_port", 22))
    pool.disconnect(host, username, password, port)
    return {"disconnected": True}


@router.post("/scan")
async def scan_from_device(data: dict):
    """Scan for downstream devices from a connected device."""
    host = data.get("host", "")
    username = data.get("username", "admin")
    password = data.get("password", "")
    port = data.get("port", data.get("ssh_port", 22))

    if not host:
        raise HTTPException(status_code=400, detail="host is required")

    from core.mac_vendor import lookup_vendor
    import re as _re

    devices = []

    # ARP scan from device
    try:
        out = await pool.execute(host, username, password, "arp -a 2>/dev/null; ip neigh show 2>/dev/null", port)
        for line in out.split("\n"):
            ip = _re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
            mac = _re.search(r'([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', line)
            if ip and not ip.group(1).startswith(("127.", "0.", "169.", "255.")):
                m = mac.group(0) if mac else ""
                devices.append({"ip": ip.group(1), "mac": m, "mac_vendor": lookup_vendor(m), "source": "arp"})
    except Exception:
        pass

    # DHCP leases
    try:
        out = await pool.execute(host, username, password, "cat /var/lib/misc/dnsmasq.leases 2>/dev/null | head -20; cat /tmp/dhcpd.leases 2>/dev/null | head -20", port)
        for line in out.split("\n"):
            ip = _re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
            mac = _re.search(r'([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}', line)
            if ip and not ip.group(1).startswith(("127.", "0.", "169.", "255.")):
                m = mac.group(0) if mac else ""
                devices.append({"ip": ip.group(1), "mac": m, "mac_vendor": lookup_vendor(m), "source": "dhcp"})
    except Exception:
        pass

    # Deduplicate
    seen = set()
    unique = []
    for d in devices:
        k = d["ip"] or d["mac"]
        if k and k not in seen:
            seen.add(k)
            unique.append(d)

    return {"devices": unique[:30], "count": len(unique[:30])}


@router.post("/tunnel-check")
async def tunnel_check(data: dict):
    """Check if target is reachable from jump host, return ssh -L command."""
    host = data.get("host", "")
    username = data.get("username", "admin")
    password = data.get("password", "")
    target = data.get("target", "")

    if not host or not target:
        raise HTTPException(status_code=400, detail="host and target are required")

    reachable = False
    try:
        out = await pool.execute(host, username, password,
            f"ping -c 2 -W 2 {target} 2>&1", 22, timeout=10)
        reachable = "bytes from" in out.lower()
    except Exception:
        pass

    if not reachable:
        subnet = ".".join(target.split(".")[:3]) + ".0"
        try:
            await pool.execute(host, username, password,
                f"route add -net {subnet} netmask 255.255.255.0 eth0 2>&1; ip route add {subnet}/24 dev eth0 2>&1; echo DONE",
                22, timeout=5)
            import asyncio; await asyncio.sleep(0.5)
            out2 = await pool.execute(host, username, password,
                f"ping -c 2 -W 2 {target} 2>&1", 22, timeout=10)
            reachable = "bytes from" in out2.lower()
        except Exception:
            pass

    return {
        "reachable": reachable,
        "command": f"ssh -L 8888:{target}:80 {username}@{host} -p 22",
        "tip": "Run this in your terminal, then open http://localhost:8888" if reachable
               else f"Cannot reach {target} from this CPE."
    }


@router.post("/tunnel-open")
async def tunnel_open(data: dict):
    """Open an SSH tunnel to a downstream device and return local URL."""
    host = data.get("host", "")
    username = data.get("username", "admin")
    password = data.get("password", "")
    target = data.get("target", "")
    target_port = int(data.get("target_port", 80))
    idle_timeout = int(data.get("idle_timeout", 120))

    if not host or not target:
        raise HTTPException(status_code=400, detail="host and target required")

    try:
        result = await open_tunnel(host, username, password, target, target_port, idle_timeout)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tunnels")
async def tunnels_list():
    """List all currently open SSH tunnels."""
    return {"tunnels": list_tunnels()}


@router.delete("/tunnel/{tunnel_id}")
async def tunnel_close(tunnel_id: int):
    """Close an open SSH tunnel."""
    ok = close_tunnel(tunnel_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Tunnel not found")
    return {"closed": True, "id": tunnel_id}
