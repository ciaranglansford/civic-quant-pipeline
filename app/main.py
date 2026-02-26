from contextlib import asynccontextmanager

from fastapi import FastAPI

from .db import init_db
from .logging_utils import configure_logging
from .routers.admin import router as admin_router
from .routers.ingest import router as ingest_router
from .schemas import HealthResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Civicquant Intelligence Pipeline", version="0.1.0", lifespan=lifespan)

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    app.include_router(ingest_router)
    app.include_router(admin_router)
    return app


app = create_app()

