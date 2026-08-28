"""
Notification service — wraps Resend for email and supports in-app notifications.
If RESEND_API_KEY is not set, email is simulated and logged.
"""
from typing import Optional
from sqlalchemy.orm import Session
from app.database.models import (
    Notification, NotificationChannel, NotificationStatus, MaintenanceTask, Vehicle
)
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class NotificationService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def send(
        self,
        recipient: str,
        channel: NotificationChannel,
        subject: str,
        message: str,
        related_entity_type: Optional[str] = None,
        related_entity_id: Optional[str] = None,
    ) -> Notification:
        notification = Notification(
            recipient=recipient,
            channel=channel,
            subject=subject,
            message=message,
            status=NotificationStatus.PENDING,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
        )
        self.db.add(notification)
        self.db.flush()

        if channel == NotificationChannel.EMAIL:
            status = self._send_email(recipient, subject, message)
        else:
            # IN_APP notifications are persisted in the DB directly
            status = NotificationStatus.SENT

        notification.status = status
        self.db.flush()
        return notification

    def _send_email(self, to: str, subject: str, message: str) -> NotificationStatus:
        if not self.settings.resend_api_key:
            logger.info("email_simulated", to=to, subject=subject)
            return NotificationStatus.SIMULATED

        try:
            import resend
            resend.api_key = self.settings.resend_api_key
            resend.Emails.send({
                "from": self.settings.resend_from_email,
                "to": to,
                "subject": subject,
                "text": message,
            })
            logger.info("email_sent", to=to, subject=subject)
            return NotificationStatus.SENT
        except Exception as e:
            logger.error("email_failed", to=to, error=str(e))
            return NotificationStatus.FAILED

    def notify_critical_incident(self, incident, vehicle: Vehicle) -> None:
        subject = f"[CRITICAL] {vehicle.fleet_number} — {incident.category or 'Issue'} Requires Immediate Attention"
        message = (
            f"A CRITICAL maintenance incident has been reported for vehicle {vehicle.fleet_number} "
            f"({vehicle.year} {vehicle.make} {vehicle.model}).\n\n"
            f"Report: {incident.description}\n\n"
            f"The vehicle has been taken OUT OF SERVICE pending manager approval.\n"
            f"Please review and approve the maintenance task in FleetPilot."
        )
        self.send("Fleet Manager", NotificationChannel.IN_APP, subject, message, "incident", str(incident.id))
        self.send("Fleet Manager", NotificationChannel.EMAIL, subject, message, "incident", str(incident.id))

    def notify_task_approved(self, task: MaintenanceTask, vehicle: Optional[Vehicle]) -> None:
        fleet_num = vehicle.fleet_number if vehicle else "Unknown"
        subject = f"Maintenance Task Approved — {fleet_num}"
        message = f"Task '{task.title}' has been approved and is now ready for execution."
        self.send("Maintenance Team", NotificationChannel.IN_APP, subject, message, "maintenance_task", str(task.id))
