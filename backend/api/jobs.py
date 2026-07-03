from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.connection import get_session
from models.job import ConfigJob, ConfigJobItem, JobStatus
from datetime import datetime

router = APIRouter()


@router.get("")
async def list_jobs(
    status: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(ConfigJob)
    if status:
        stmt = stmt.where(ConfigJob.status == status)
    result = await session.execute(stmt.order_by(ConfigJob.created_at.desc()).limit(50))
    jobs = result.scalars().all()
    return [
        {
            "id": j.id,
            "site_id": j.site_id,
            "name": j.name,
            "status": j.status.value if j.status else "unknown",
            "total_devices": j.total_devices,
            "completed_devices": j.completed_devices,
            "failed_devices": j.failed_devices,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        }
        for j in jobs
    ]


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(ConfigJob).where(ConfigJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    items_result = await session.execute(
        select(ConfigJobItem).where(ConfigJobItem.job_id == job_id)
    )
    items = items_result.scalars().all()

    return {
        "id": job.id,
        "site_id": job.site_id,
        "name": job.name,
        "status": job.status.value if job.status else "unknown",
        "total_devices": job.total_devices,
        "completed_devices": job.completed_devices,
        "failed_devices": job.failed_devices,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "items": [
            {
                "id": item.id,
                "device_id": item.device_id,
                "device_ip": item.device_ip,
                "status": item.status.value if item.status else "unknown",
                "error_message": item.error_message,
                "completed_at": item.completed_at.isoformat() if item.completed_at else None,
            }
            for item in items
        ],
    }


@router.post("")
async def create_job(
    data: dict,
    session: AsyncSession = Depends(get_session),
):
    job = ConfigJob(
        site_id=data.get("site_id"),
        name=data.get("name", "Untitled Job"),
        status=JobStatus.QUEUED,
        template_id=data.get("template_id"),
        total_devices=data.get("total_devices", 0),
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    devices = data.get("devices", [])
    for d in devices:
        item = ConfigJobItem(
            job_id=job.id,
            device_id=d.get("device_id", ""),
            device_ip=d.get("device_ip", d.get("ip", "")),
            status=JobStatus.QUEUED,
        )
        session.add(item)

    job.total_devices = len(devices)
    await session.commit()

    return {"id": job.id, "name": job.name, "status": "queued"}
