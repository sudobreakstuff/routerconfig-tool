import asyncio
import platform
import re
import socket
from dataclasses import dataclass, field


MAC_REGEX = re.compile(r'([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}')


def extract_mac(text: str) -> str:
    m = MAC_REGEX.search(text)
    return m.group(0) if m else ""


def extract_macs(text: str) -> list[str]:
    return MAC_REGEX.findall(text)


@dataclass
class DiscoveredDevice:
    ip: str
    mac: str = ""
    hostname: str = ""
    vendor: str = ""
    mac_vendor: str = ""
    open_ports: list[int] = field(default_factory=list)
    brand_hint: str = "unknown"


async def _run_command(cmd: list[str], timeout: int = 15) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = stdout.decode(errors="replace").strip()
        if not output and stderr:
            output = stderr.decode(errors="replace").strip()
        return output
    except Exception:
        return ""


async def _arp_scan() -> list[DiscoveredDevice]:
    devices: list[DiscoveredDevice] = []
    from core.mac_vendor import lookup_vendor

    if platform.system() == "Windows":
        output = await _run_command(["arp", "-a"])
        for line in output.split("\n"):
            parts = line.split()
            if len(parts) >= 3:
                ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                mac = extract_mac(line)
                if ip_match:
                    devices.append(DiscoveredDevice(
                        ip=ip_match.group(1), mac=mac,
                        mac_vendor=lookup_vendor(mac),
                    ))
    else:
        # ip neigh show: "IP dev IFACE lladdr MAC STATE"
        output = await _run_command(["ip", "neigh", "show"])
        for line in output.split("\n"):
            ip_match = re.search(r'^(\d+\.\d+\.\d+\.\d+)', line)
            if ip_match:
                ip = ip_match.group(1)
                if ip.startswith("127."):
                    continue
                mac = extract_mac(line)
                devices.append(DiscoveredDevice(
                    ip=ip, mac=mac, mac_vendor=lookup_vendor(mac),
                ))

        # Fallback to arp -n
        if not devices:
            output2 = await _run_command(["arp", "-n"])
            for line in output2.split("\n"):
                ip_match = re.search(r'^(\d+\.\d+\.\d+\.\d+)', line)
                if ip_match:
                    ip = ip_match.group(1)
                    if ip.startswith("127."):
                        continue
                    mac = extract_mac(line)
                    devices.append(DiscoveredDevice(
                        ip=ip, mac=mac, mac_vendor=lookup_vendor(mac),
                    ))

    return devices


async def _probe_port(ip: str, port: int, timeout: float = 2.0) -> bool:
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


async def _probe_ports(ip: str) -> list[int]:
    KEY_PORTS = [80, 443, 22, 23, 8291, 8728, 8080, 8443]
    results = await asyncio.gather(*[_probe_port(ip, p, 1.5) for p in KEY_PORTS])
    return [KEY_PORTS[i] for i, open_ in enumerate(results) if open_]


async def _identify_brand(ip: str) -> str:
    import httpx
    try:
        async with httpx.AsyncClient(timeout=4, verify=False) as client:
            resp = await client.get(f"http://{ip}/")
            text = resp.text[:3000].lower()
            if "mikrotik" in text or "routeros" in text: return "mikrotik"
            if "tplink" in text or "tp-link" in text: return "tplink"
            if "ubiquiti" in text or "unifi" in text: return "ubiquiti"
    except Exception:
        pass
    return "unknown"


async def discover_devices(subnet: str = "192.168.0.0/24") -> list[DiscoveredDevice]:
    devices = await _arp_scan()
    for d in devices[:20]:
        d.open_ports = await _probe_ports(d.ip)
        if 8291 in d.open_ports or 8728 in d.open_ports:
            d.brand_hint = "mikrotik"
        elif d.brand_hint == "unknown":
            d.brand_hint = await _identify_brand(d.ip)
    own = _get_local_ips()
    devices = [d for d in devices if d.ip not in own]
    return devices


async def ping_host(ip: str, timeout: int = 3) -> bool:
    if platform.system() == "Windows":
        cmd = ["ping", "-n", "1", "-w", str(timeout * 1000), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(timeout), ip]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )
        code = await asyncio.wait_for(proc.wait(), timeout=timeout + 3)
        return code == 0
    except Exception:
        return False


def _get_local_ips() -> set[str]:
    ips = {"127.0.0.1", "127.0.1.1"}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ip = info[4][0]
            if not ip.startswith("127."): ips.add(ip)
    except Exception: pass
    return ips
