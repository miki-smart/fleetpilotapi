from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.dependencies import get_db
from app.database.models import Notification

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
def list_notifications(db: Session = Depends(get_db)):
    notifications = db.query(Notification).order_by(Notification.created_at.desc()).limit(50).all()
    return {"success": True, "data": [_notification(n) for n in notifications]}


@router.get("/agent-actions")
def list_agent_actions(db: Session = Depends(get_db)):
    from app.database.models import AgentAction
    actions = db.query(AgentAction).order_by(AgentAction.created_at.desc()).limit(50).all()
    return {
        "success": True,
        "data": [
            {
                "id": str(a.id),
                "action_type": a.action_type,
                "description": a.description,
                "status": a.status,
                "tool_name": a.tool_name,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "incident_id": str(a.incident_id) if a.incident_id else None,
            }
            for a in actions
        ],
    }


def _notification(n: Notification) -> dict:
    return {
        "id": str(n.id),
        "recipient": n.recipient,
        "channel": n.channel,
        "subject": n.subject,
        "message": n.message,
        "status": n.status,
        "related_entity_type": n.related_entity_type,
        "related_entity_id": n.related_entity_id,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }
