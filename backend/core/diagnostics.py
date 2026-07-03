from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.drivers.base import RouterConnection
from core.drivers.factory import DriverFactory
from core.discovery import ping_host, _probe_ports


@dataclass
class TestResult:
    name: str
    passed: bool
    message: str
    detail: str = ""
    severity: str = "info"


@dataclass  
class DiagnosticResult:
    device_id: str | None = None
    baseline_id: str | None = None
    is_healthy: bool = True
    issues_found: int = 0
    warnings_found: int = 0
    tests: list[TestResult] = field(default_factory=list)
    config_diff: list[dict] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())


async def run_diagnostic_tests(
    device_id: str,
    host: str = "",
    username: str = "admin",
    password: str = "",
    brand: str = "generic",
    ssh_port: int = 22,
    web_port: int = 80,
    baseline_config: dict | None = None,
) -> DiagnosticResult:
    result = DiagnosticResult(device_id=device_id)

    if not host:
        result.tests.append(TestResult(name="Host", passed=False, message="No IP address provided", severity="critical"))
        result.issues_found += 1
        result.is_healthy = False
        return result

    # Test 1: Ping
    reachable = await ping_host(host)
    result.tests.append(TestResult(
        name="Ping Test",
        passed=reachable,
        message="Device is reachable" if reachable else "Device is NOT reachable - check connectivity",
        severity="critical" if not reachable else "info",
    ))
    if not reachable:
        result.issues_found += 1
        result.is_healthy = False
        return result

    # Test 2: Port scan
    ports = await _probe_ports(host)
    ssh_open = 22 in ports or ssh_port in ports
    http_open = 80 in ports or 443 in ports
    port_status = f"SSH: {'open' if ssh_open else 'closed'}, HTTP: {'open' if http_open else 'closed'}"
    result.tests.append(TestResult(
        name="Port Scan",
        passed=ssh_open or http_open,
        message=port_status,
        detail=f"Ports: {','.join(str(p) for p in ports)}" if ports else "",
        severity="warning" if not ssh_open else "info",
    ))
    if not ssh_open and not http_open:
        result.warnings_found += 1

    # Test 3: Try to connect via SSH
    conn = RouterConnection(host=host, port=ssh_port, username=username, password=password, web_port=web_port)
    driver = DriverFactory.create(brand, conn)

    ssh_connected = await driver.connect()
    if ssh_connected:
        result.tests.append(TestResult(
            name="SSH Login", passed=True,
            message=f"Authenticated as {username}",
        ))

        # Test 4: Get device info
        try:
            info = await driver.get_info()
            result.tests.append(TestResult(
                name="Device Info", passed=True,
                message=f"Model: {info.model}, FW: {info.firmware_version}",
                detail=f"MAC: {info.mac_address}, Uptime: {info.uptime}",
            ))
        except Exception:
            result.tests.append(TestResult(
                name="Device Info", passed=False,
                message="Could not read device information", severity="warning",
            ))
            result.warnings_found += 1

        # Test 5: Get running state
        try:
            state = await driver.get_running_state()
            dhcp_check = state.dhcp_enabled
            result.tests.append(TestResult(
                name="DHCP Server",
                passed=not dhcp_check,
                message=f"DHCP is {'ENABLED (should be OFF behind CPE)' if dhcp_check else 'disabled (correct)'}",
                severity="critical" if dhcp_check else "info",
            ))
            if dhcp_check:
                result.issues_found += 1

            result.tests.append(TestResult(
                name="WiFi Radio",
                passed=state.wifi_enabled,
                message=f"WiFi is {'ON' if state.wifi_enabled else 'OFF'}",
                severity="critical" if not state.wifi_enabled else "info",
            ))
            if not state.wifi_enabled:
                result.issues_found += 1

            result.tests.append(TestResult(
                name="Bridge Mode",
                passed=state.bridge_mode,
                message="Bridge/AP mode is enabled" if state.bridge_mode else "Bridge mode is OFF (NAT active)",
                severity="warning" if not state.bridge_mode else "info",
            ))
            if not state.bridge_mode:
                result.warnings_found += 1

            if state.ssids:
                result.tests.append(TestResult(
                    name="SSIDs",
                    passed=len(state.ssids) > 0,
                    message=f"Found {len(state.ssids)} SSID(s): {', '.join(str(s.get('ssid', s)) for s in state.ssids)}",
                ))
        except Exception:
            result.tests.append(TestResult(
                name="Running State", passed=False,
                message="Could not read device state", severity="warning",
            ))
            result.warnings_found += 1

        # Test 6: Internet connectivity (from the device)
        try:
            ping_out = await driver._ssh_execute("ping -c 2 -W 2 8.8.8.8 2>/dev/null || echo 'FAILED'")
            has_internet = "FAILED" not in ping_out and ("bytes from" in ping_out.lower() or "received" in ping_out)
            result.tests.append(TestResult(
                name="Internet Connectivity",
                passed=has_internet,
                message="Device can reach internet (8.8.8.8)" if has_internet else "Device cannot reach internet",
                severity="critical" if not has_internet else "info",
            ))
            if not has_internet:
                result.issues_found += 1
        except Exception:
            pass

        # Test 7: DNS test from device
        try:
            dns_out = await driver._ssh_execute("nslookup google.com 2>/dev/null || ping -c 1 google.com 2>/dev/null | head -1 || echo 'FAILED'")
            dns_ok = "FAILED" not in dns_out and "google" in dns_out.lower()
            result.tests.append(TestResult(
                name="DNS Resolution",
                passed=dns_ok,
                message="DNS is working" if dns_ok else "DNS resolution failed",
                severity="warning" if not dns_ok else "info",
            ))
            if not dns_ok:
                result.warnings_found += 1
        except Exception:
            pass

        # Test 8: PPPoE status (important for Jenny Internet)
        try:
            ppp_raw = await driver._ssh_execute("cat /tmp/system.cfg 2>/dev/null | grep ppp || echo ''")
            if ppp_raw.strip():
                ppp_up = "status=enabled" in ppp_raw and "ppp.1.status=enabled" in ppp_raw
                ppp_user = re.search(r'ppp\.1\.name=(\S+)', ppp_raw)
                result.tests.append(TestResult(
                    name="PPPoE Connection",
                    passed=ppp_up,
                    message=f"PPPoE is up ({ppp_user.group(1) if ppp_user else 'unknown'})" if ppp_up else "PPPoE is configured but may be down",
                    severity="critical" if not ppp_up else "info",
                ))
                if not ppp_up:
                    result.issues_found += 1
        except Exception:
            pass

        await driver.disconnect()

    else:
        result.tests.append(TestResult(
            name="SSH Login", passed=False,
            message="Could not authenticate via SSH (device may not have SSH enabled)",
            severity="warning" if http_open else "critical",
        ))
        if not http_open:
            result.issues_found += 1
        else:
            result.warnings_found += 1

    # Test 9: Config comparison against baseline
    if baseline_config and ssh_connected:
        try:
            await driver.connect()
            current = await driver.get_running_config()
            await driver.disconnect()

            diffs = _diff_configs(baseline_config, current)
            if diffs:
                result.config_diff = diffs
                critical_diffs = [d for d in diffs if d["severity"] == "critical"]
                result.tests.append(TestResult(
                    name="Config Comparison",
                    passed=len(critical_diffs) == 0,
                    message=f"{len(diffs)} config differences found ({len(critical_diffs)} critical)" if diffs else "Config matches baseline",
                    severity="critical" if critical_diffs else "warning" if diffs else "info",
                ))
                result.issues_found += len(critical_diffs)
                result.warnings_found += len(diffs) - len(critical_diffs)
            else:
                result.tests.append(TestResult(
                    name="Config Comparison", passed=True,
                    message="Config matches baseline",
                ))
        except Exception:
            pass

    result.is_healthy = result.issues_found == 0
    return result


def _diff_configs(baseline: dict, current: dict) -> list[dict]:
    diffs = []
    base_str = str(baseline.get("raw", baseline))
    curr_str = str(current.get("raw", current))
    if base_str == curr_str:
        return []

    base_lines = base_str.split("\n")
    curr_lines = curr_str.split("\n")
    for i, (b, c) in enumerate(zip(base_lines, curr_lines)):
        if b != c and b.strip() and c.strip():
            severity = "warning"
            if "password" in b.lower() or "secret" in b.lower():
                continue
            if "dhcp" in b.lower() and "enabled" in b.lower():
                severity = "critical"
            diffs.append({"path": f"line {i+1}", "baseline": b.strip()[:80], "current": c.strip()[:80], "severity": severity})
    return diffs[:20]
