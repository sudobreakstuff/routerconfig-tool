import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


DATA_DIR = Path(os.environ.get("RC_DATA_DIR", Path.home() / ".routerconfig"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR / 'routerconfig.db'}"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    from models.device import Device
    from models.site import Site
    from models.baseline import Baseline
    from models.config_template import ConfigTemplate
    from models.job import ConfigJob, ConfigJobItem
    from models.isp_profile import ISPProfile
    from models.diagnostic_report import DiagnosticReport
    from models.connection_profile import ConnectionProfile

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
