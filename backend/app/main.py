from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.exceptions import FleetPilotError
from app.database.session import engine
from app.database.models import Base, AgentActionType
from app.automation.scheduler import start_scheduler, shutdown_scheduler
from app.api.routes import dashboard, vehicles, maintenance, incidents, notifications, automation
from app.api.routes import settings as settings_routes

configure_logging()
logger = get_logger(__name__)

settings = get_settings()


def _ensure_enum_values() -> None:
    """create_all never alters existing Postgres enum types; add any values the
    code knows about that an older database is missing."""
    if engine.dialect.name != "postgresql":
        return
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            for value in AgentActionType:
                conn.execute(text(f"ALTER TYPE agentactiontype ADD VALUE IF NOT EXISTS '{value.value}'"))
    except Exception as e:
        logger.warning("enum_sync_skipped", error=str(e)[:200])


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("fleetpilot_starting", env=settings.app_env)
    Base.metadata.create_all(bind=engine)
    _ensure_enum_values()
    logger.info("database_tables_ready")
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(
    title="FleetPilot AI",
    description="AI-powered fleet maintenance coordination agent",
    version="1.1.0",
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
    return {"status": "ok", "service": "FleetPilot AI", "version": app.version}
