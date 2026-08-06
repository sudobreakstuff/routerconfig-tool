import uvicorn
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import devices, configs, discovery, diagnostics, templates, remote, actions, jobs, isp, settings
from core.auth import get_api_token, require_token
from database.connection import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    get_api_token()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="RouterConfig Pro",
        version="1.0.0",
        description="Multi-vendor router auto-configuration and remote management",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "null",
        ],
        allow_origin_regex=r"^file://.*$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    protected = [Depends(require_token)]
    app.include_router(devices.router, prefix="/api/devices", tags=["Devices"], dependencies=protected)
    app.include_router(configs.router, prefix="/api/configs", tags=["Config"], dependencies=protected)
    app.include_router(discovery.router, prefix="/api/discovery", tags=["Discovery"], dependencies=protected)
    app.include_router(diagnostics.router, prefix="/api/diagnostics", tags=["Diagnostics"], dependencies=protected)
    app.include_router(templates.router, prefix="/api/templates", tags=["Templates"], dependencies=protected)
    app.include_router(remote.router, prefix="/api/remote", tags=["Remote Access"], dependencies=protected)
    app.include_router(actions.router, prefix="/api/actions", tags=["Actions"], dependencies=protected)
    app.include_router(jobs.router, prefix="/api/jobs", tags=["Jobs"], dependencies=protected)
    app.include_router(isp.router, prefix="/api/isp", tags=["ISP"], dependencies=protected)
    # settings is intentionally unprotected so the renderer can bootstrap its token.
    app.include_router(settings.router, prefix="/api/settings", tags=["Settings"])

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": "1.0.0"}

    return app


app = create_app()


def main():
    uvicorn.run(app, host="127.0.0.1", port=7933, reload=False)


if __name__ == "__main__":
    main()
