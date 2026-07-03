from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.connection import get_session
from models.isp_profile import ISPProfile
from isp_adapters.registry import ISPAdapterRegistry
from isp_adapters.base import DeviceUploadPayload
from services.device_service import DeviceService
from core.encryption import encrypt, decrypt

router = APIRouter()


@router.get("/adapters")
async def list_adapters():
    return [{"name": name} for name in ISPAdapterRegistry.available_adapters()]


@router.get("/profiles")
async def list_profiles(
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(ISPProfile).where(ISPProfile.is_active == True))
    profiles = result.scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "adapter_name": p.adapter_name,
            "dhcp_server_ip": p.dhcp_server_ip,
            "dns_servers": p.dns_servers,
            "wan_vlan": p.wan_vlan,
            "wan_pppoe": p.wan_pppoe,
            "custom_settings": p.custom_settings,
        }
        for p in profiles
    ]


@router.post("/profiles")
async def create_profile(
    data: dict,
    session: AsyncSession = Depends(get_session),
):
    if data.get("upload_api_key"):
        data["upload_api_key_encrypted"] = encrypt(data.pop("upload_api_key"))

    profile = ISPProfile(**data)
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return {"id": profile.id, "name": profile.name}


@router.put("/profiles/{profile_id}")
async def update_profile(
    profile_id: str,
    data: dict,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(ISPProfile).where(ISPProfile.id == profile_id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    if data.get("upload_api_key"):
        data["upload_api_key_encrypted"] = encrypt(data.pop("upload_api_key"))

    for key, val in data.items():
        if hasattr(profile, key) and key != "id":
            setattr(profile, key, val)

    await session.commit()
    return {"id": profile.id, "name": profile.name}


@router.delete("/profiles/{profile_id}")
async def delete_profile(
    profile_id: str,
    session: AsyncSession = Depends(get_session),
):
    from sqlalchemy import delete
    await session.execute(delete(ISPProfile).where(ISPProfile.id == profile_id))
    await session.commit()
    return {"success": True}


@router.post("/upload-device")
async def upload_device(
    data: dict,
    session: AsyncSession = Depends(get_session),
):
    device_id = data.get("device_id")
    profile_id = data.get("profile_id")

    device = await DeviceService.get_by_id(session, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    profile = None
    if profile_id:
        result = await session.execute(select(ISPProfile).where(ISPProfile.id == profile_id))
        profile = result.scalar_one_or_none()

    if not profile and device.site_id:
        result = await session.execute(select(ISPProfile).where(ISPProfile.id == device.site_id))
        profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(status_code=400, detail="No ISP profile found. Configure one in Settings or provide profile_id.")

    adapter = ISPAdapterRegistry.create(
        profile.adapter_name,
        api_base_url=profile.upload_endpoint or "",
        api_key=decrypt(profile.upload_api_key_encrypted) if profile.upload_api_key_encrypted else "",
    )

    if not adapter:
        raise HTTPException(status_code=400, detail=f"Unknown adapter: {profile.adapter_name}")

    payload = DeviceUploadPayload(
        device_id=device.id,
        site_id=device.site_id,
        mac_address=device.mac_address or "",
        ip_address=device.ip_address or "",
        brand=device.brand.value if device.brand else "unknown",
        model=device.model or "",
        ssid=decrypt(device.wifi_ssid_encrypted) if device.wifi_ssid_encrypted else "",
        admin_username=decrypt(device.admin_user_encrypted) if device.admin_user_encrypted else "admin",
        firmware_version=device.firmware_version or "",
        custom_fields=data.get("custom_fields", {}),
    )

    success = await adapter.upload_device_info(payload)
    return {"success": success, "device_id": device_id}


@router.post("/test/{adapter_name}")
async def test_adapter(
    adapter_name: str,
    data: dict | None = None,
):
    config = data or {}
    adapter = ISPAdapterRegistry.create(
        adapter_name,
        api_base_url=config.get("api_base_url", ""),
        api_key=config.get("api_key", ""),
    )
    if not adapter:
        raise HTTPException(status_code=400, detail=f"Unknown adapter: {adapter_name}")

    success = await adapter.test_connection()
    return {"success": success, "adapter": adapter_name}
