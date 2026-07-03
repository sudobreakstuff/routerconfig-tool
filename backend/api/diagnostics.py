from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import re as _re

from database.connection import get_session
from models.diagnostic_report import DiagnosticReport
from models.baseline import Baseline
from models.device import Device
from core.diagnostics import run_diagnostic_tests
from core.drivers.base import RouterConnection
from core.drivers.factory import DriverFactory
from datetime import datetime

router = APIRouter()


@router.post("/run")
async def run_diagnostics(data: dict, session: AsyncSession = Depends(get_session)):
    device_id = data.get("device_id", "")
    host = data.get("host", data.get("ip_address", ""))
    username = data.get("username", data.get("admin_username", "admin"))
    password = data.get("password", data.get("admin_password", ""))
    brand = data.get("brand", "generic")

    # If device_id is provided but no host, look up the device
    if not host and device_id:
        result = await session.execute(select(Device).where(Device.id == device_id))
        device = result.scalar_one_or_none()
        if device:
            host = device.ip_address or ""
            brand = (device.brand.value if hasattr(device.brand, 'value') else str(device.brand)) if device.brand else "generic"
            from core.encryption import decrypt
            username = decrypt(device.admin_user_encrypted) if device.admin_user_encrypted else "admin"
            password = decrypt(device.admin_password_encrypted) if device.admin_password_encrypted else ""

    if not host and not device_id:
        raise HTTPException(status_code=400, detail="device_id or host is required")

    # Get latest baseline if device_id exists
    baseline_config = None
    baseline_id = None
    if device_id:
        bl_result = await session.execute(
            select(Baseline).where(Baseline.device_id == device_id).order_by(Baseline.created_at.desc()).limit(1)
        )
        baseline = bl_result.scalar_one_or_none()
        if baseline:
            baseline_config = baseline.full_config
            baseline_id = baseline.id

    diag = await run_diagnostic_tests(
        device_id=device_id,
        host=host,
        username=username,
        password=password,
        brand=brand,
        baseline_config=baseline_config,
    )

    # Save report
    report = DiagnosticReport(
        device_id=device_id or "manual",
        baseline_id=baseline_id,
        current_config={},
        current_state={},
        differences=[{
            "path": d["path"], "severity": d["severity"],
            "baseline_value": d.get("baseline", ""), "current_value": d.get("current", ""),
        } for d in diag.config_diff],
        health_checks=[{
            "name": t.name, "passed": t.passed, "message": t.message, "severity": t.severity,
        } for t in diag.tests],
        issues_found=diag.issues_found,
        warnings_found=diag.warnings_found,
        is_healthy=diag.is_healthy,
    )
    session.add(report)
    await session.commit()

    return {
        "device_id": device_id,
        "baseline_id": baseline_id,
        "is_healthy": diag.is_healthy,
        "issues_found": diag.issues_found,
        "warnings_found": diag.warnings_found,
        "tests": [{"name": t.name, "passed": t.passed, "message": t.message, "detail": t.detail, "severity": t.severity} for t in diag.tests],
        "differences": diag.config_diff,
        "report_id": report.id,
    }


@router.get("/reports/{device_id}")
async def get_reports(device_id: str, session: AsyncSession = Depends(get_session)):
    stmt = select(DiagnosticReport).where(
        DiagnosticReport.device_id == device_id
    ).order_by(DiagnosticReport.created_at.desc()).limit(20)
    result = await session.execute(stmt)
    reports = result.scalars().all()
    return [{
        "id": r.id, "device_id": r.device_id, "baseline_id": r.baseline_id,
        "is_healthy": r.is_healthy, "issues_found": r.issues_found,
        "warnings_found": r.warnings_found, "differences": r.differences,
        "health_checks": r.health_checks,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }     for r in reports]


@router.post("/bandwidth-test")
async def bandwidth_test(data: dict):
    """Proper internet speed test via the remote device.
    Ping = ICMP latency from the device.
    Download = pull test file from speedtest server through the device.
    Upload = push data to test server through the device."""
    import paramiko, time as _time

    host = data.get("host", "")
    username = data.get("username", "admin")
    password = data.get("password", "")
    ssh_port = data.get("ssh_port", 22)

    if not host:
        raise HTTPException(status_code=400, detail="host is required")

    r = {"download_mbps": 0, "upload_mbps": 0, "latency_ms": 0, "method": ""}

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(host, port=ssh_port, username=username, password=password, timeout=15, banner_timeout=10)
    except Exception as e:
        return {**r, "method": f"SSH failed: {str(e)[:80]}", "error": "auth"}

    try:
        # --- PING ---
        try:
            _s, _o, _e = ssh.exec_command("ping -c 6 -W 2 1.1.1.1 2>&1", timeout=20)
            out = _o.read().decode(errors="replace")
            times = _re.findall(r'time=(\d+\.?\d*)', out)
            if times:
                r["latency_ms"] = round(sum(float(t) for t in times) / len(times), 1)
            else:
                m = _re.search(r'avg[=/\s]+(\d+\.?\d*)', out)
                if m: r["latency_ms"] = float(m.group(1))
        except Exception:
            pass

        # --- DOWNLOAD SPEED ---
        for url in [
            "http://speedtest.tele2.net/1MB.zip",
            "http://ipv4.download.thinkbroadband.com/1MB.zip",
        ]:
            try:
                _s, _o, _e = ssh.exec_command(
                    f"wget -q -O /dev/null '{url}' 2>&1; echo SPEEDEND", timeout=30
                )
                t0 = _time.time(); out = _o.read().decode(errors="replace"); el = _time.time() - t0
                if "SPEEDEND" in out and 0.5 < el < 30:
                    r["download_mbps"] = round(8.0 / el, 1)
                    r["method"] = f"Download 1MB ({el:.1f}s via wget)"
                    break
            except Exception:
                pass

            try:
                _s, _o, _e = ssh.exec_command(
                    f"curl -s -o /dev/null --max-time 20 '{url}' 2>&1; echo SPEEDEND", timeout=30
                )
                t0 = _time.time(); out = _o.read().decode(errors="replace"); el = _time.time() - t0
                if "SPEEDEND" in out and 0.5 < el < 30:
                    r["download_mbps"] = round(8.0 / el, 1)
                    r["method"] = f"Download 1MB ({el:.1f}s via curl)"
                    break
            except Exception:
                pass

        # --- UPLOAD SPEED ---
        if r["download_mbps"] > 0:
            try:
                cmd = ("dd if=/dev/urandom of=/tmp/spdup.bin bs=256K count=1 2>/dev/null && "
                       "(wget -q -O /dev/null --post-file=/tmp/spdup.bin http://httpbin.org/post 2>&1 || "
                       "curl -s -o /dev/null --max-time 20 -X POST --data-binary @/tmp/spdup.bin http://httpbin.org/post 2>&1); "
                       "rm -f /tmp/spdup.bin; echo SPEEDEND")
                _s, _o, _e = ssh.exec_command(cmd, timeout=35)
                t0 = _time.time(); out = _o.read().decode(errors="replace"); el = _time.time() - t0
                if "SPEEDEND" in out and 0.5 < el < 30:
                    r["upload_mbps"] = round(2.0 / el, 1)
                    r["method"] += " + Upload 256KB"
            except Exception:
                pass

        # --- FALLBACK: SSH throughput ---
        if r["download_mbps"] == 0:
            try:
                _s, _o, _e = ssh.exec_command(
                    "dd if=/dev/zero bs=256K count=4 2>/dev/null | base64 2>/dev/null; echo SPEEDEND", timeout=15
                )
                t0 = _time.time(); out = _o.read().decode(errors="replace"); el = _time.time() - t0
                if "SPEEDEND" in out and el > 0.3:
                    r["download_mbps"] = round(8.0 / el, 1)
                    r["method"] = f"SSH throughput ({el:.1f}s)"
            except Exception:
                pass

        if not r["download_mbps"]:
            r["method"] = "No tools (wget/curl) on device and SSH throughput test failed"

    except Exception as e:
        r["method"] = f"Error: {str(e)[:80]}"
    finally:
        ssh.close()

    return r
