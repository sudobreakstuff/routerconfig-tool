from fastapi import APIRouter, Query

from core.discovery import discover_devices, ping_host

router = APIRouter()


@router.get("/scan")
async def scan_network(
    subnet: str = Query("192.168.0.0/24"),
):
    devices = await discover_devices(subnet)
    return [
        {
            "ip": d.ip,
            "mac": d.mac,
            "hostname": d.hostname,
            "vendor": d.vendor,
            "open_ports": d.open_ports,
            "brand_hint": d.brand_hint,
        }
        for d in devices
    ]


@router.get("/ping")
async def ping_device(
    ip: str = Query(...),
    timeout: int = Query(3),
):
    reachable = await ping_host(ip, timeout)
    return {"ip": ip, "reachable": reachable}
