from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import get_session
from services.device_service import DeviceService
from models.device import Device

router = APIRouter()


@router.get("")
async def list_devices(
    site_id: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    devices = await DeviceService.list_all(session, site_id=site_id)
    return [DeviceService.to_dict(d) for d in devices]


@router.get("/{device_id}")
async def get_device(
    device_id: str,
    include_secrets: bool = Query(False),
    session: AsyncSession = Depends(get_session),
):
    device = await DeviceService.get_by_id(session, device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return DeviceService.to_dict(device, decrypt_secrets=include_secrets)


@router.post("")
async def create_device(
    data: dict,
    session: AsyncSession = Depends(get_session),
):
    device = await DeviceService.create(session, data)
    return DeviceService.to_dict(device)


@router.put("/{device_id}")
async def update_device(
    device_id: str,
    data: dict,
    session: AsyncSession = Depends(get_session),
):
    device = await DeviceService.update(session, device_id, data)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return DeviceService.to_dict(device)


@router.delete("/{device_id}")
async def delete_device(
    device_id: str,
    session: AsyncSession = Depends(get_session),
):
    deleted = await DeviceService.delete(session, device_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"success": True}
