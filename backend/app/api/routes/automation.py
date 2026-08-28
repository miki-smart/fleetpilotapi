from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.dependencies import get_db
from app.automation.fleet_health_scan import run_fleet_health_scan

router = APIRouter(prefix="/api/automation", tags=["automation"])


@router.post("/fleet-health-scan")
async def fleet_health_scan(db: Session = Depends(get_db)):
    """
    Proactive fleet health scan endpoint.
    Callable manually from UI or by Cloud Scheduler.
    """
    result = await run_fleet_health_scan(db)
    return {"success": True, "data": result}
