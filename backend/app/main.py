from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.exceptions import FleetPilotError
from app.database.session import engine
from app.database.models import Base
from app.api.routes import dashboard, vehicles, maintenance, incidents, notifications, automation
from app.api.routes import settings as settings_routes

configure_logging()
logger = get_logger(__name__)

settings = get_settings()

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("fleetpilot_starting", env=settings.app_env)
    Base.metadata.create_all(bind=engine)
    logger.info("database_tables_ready")
    yield


app = FastAPI(
    title="FleetPilot AI",
    description="AI-powered fleet maintenance coordination agent",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(FleetPilotError)
async def fleetpilot_exception_handler(request: Request, exc: FleetPilotError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_exception", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred."}},
    )


app.include_router(dashboard.router)
app.include_router(vehicles.router)
app.include_router(maintenance.router)
app.include_router(incidents.router)
app.include_router(notifications.router)
app.include_router(automation.router)
app.include_router(settings_routes.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "FleetPilot AI"}
