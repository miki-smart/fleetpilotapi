import secrets
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.config import get_settings
from app.database.models import AgentAction, AgentActionType
from app.automation.fleet_health_scan import run_fleet_health_scan
from app.automation.scheduler import scheduler_status

router = APIRouter(prefix="/api/automation", tags=["automation"])


@router.post("/fleet-health-scan")
async def fleet_health_scan(
    db: Session = Depends(get_db),
    x_scheduler_token: Optional[str] = Header(default=None),
    source: Optional[str] = Query(default=None, description="Label for external schedulers, e.g. cloud-scheduler"),
):
    """
    Proactive fleet health scan.

    - Manual trigger from the UI: no header.
    - External schedulers (Cloud Scheduler, GitHub Actions): send `X-Scheduler-Token`
      matching SCHEDULER_TOKEN; the run is recorded as scheduler-triggered.
    """
    settings = get_settings()
    triggered_by = "manual"
    if x_scheduler_token is not None:
        if not settings.scheduler_token or not secrets.compare_digest(x_scheduler_token, settings.scheduler_token):
            raise HTTPException(status_code=401, detail={"code": "INVALID_SCHEDULER_TOKEN", "message": "Scheduler token is missing or invalid."})
        triggered_by = f"scheduler:{source or 'external'}"

    result = await run_fleet_health_scan(db, triggered_by=triggered_by)
    return {"success": True, "data": result}


@router.get("/status")
def automation_status(db: Session = Depends(get_db)):
    """Scheduler configuration, next run, and the most recent scan."""
    last = (
        db.query(AgentAction)
        .filter(AgentAction.action_type == AgentActionType.FLEET_HEALTH_SCAN)
        .order_by(AgentAction.created_at.desc())
        .first()
    )
    return {
        "success": True,
        "data": {
            "scheduler": scheduler_status(),
            "last_scan": _last_scan(last),
        },
    }


def _last_scan(action: Optional[AgentAction]) -> Optional[dict]:
    if not action:
        return None
    return {
        "id": str(action.id),
        "ran_at": action.created_at.isoformat() if action.created_at else None,
        "triggered_by": (action.tool_input or {}).get("triggered_by", "unknown"),
        "description": action.description,
        **(action.tool_output or {}),
    }
