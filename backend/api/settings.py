from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.auth import get_api_token
from database.connection import get_session, DATA_DIR, DATABASE_URL

router = APIRouter()


@router.get("/app")
async def get_app_settings():
    return {
        "data_dir": str(DATA_DIR),
        "database_url": DATABASE_URL.replace(str(DATA_DIR), "~/.routerconfig"),
        "version": "1.0.0",
        "token": get_api_token(),
    }
