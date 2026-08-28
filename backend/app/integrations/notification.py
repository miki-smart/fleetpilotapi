"""
Notification service — in-app notifications persisted to the DB, email via Resend.

Recipient resolution: the agent and business rules address people by role
("Fleet Manager"). For EMAIL, a role is resolved to FLEET_MANAGER_EMAIL. If no
Resend key is configured the email is simulated and recorded as SIMULATED so the
UI still shows what would have gone out.
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

    # --- core -------------------------------------------------------------

    def resolve_recipient(self, recipient: str, channel: NotificationChannel) -> str:
        if channel == NotificationChannel.EMAIL and "@" not in (recipient or ""):
            return self.settings.fleet_manager_email or recipient
        return recipient

    def send(
        self,
        recipient: str,
        channel: NotificationChannel,
        subject: str,
        message: str,
        related_entity_type: Optional[str] = None,
        related_entity_id: Optional[str] = None,
        html: Optional[str] = None,
    ) -> Notification:
        resolved = self.resolve_recipient(recipient, channel)
        notification = Notification(
            recipient=resolved,
            channel=channel,
            subject=subject[:300],
            message=message,
            status=NotificationStatus.PENDING,
            related_entity_type=related_entity_type,
            related_entity_id=related_entity_id,
        )
        self.db.add(notification)
        self.db.flush()

        if channel == NotificationChannel.EMAIL:
            status = self._send_email(resolved, subject, message, html)
        else:
            # IN_APP notifications are persisted in the DB directly
            status = NotificationStatus.SENT

        notification.status = status
        self.db.flush()
        return notification

    def _send_email(self, to: str, subject: str, message: str, html: Optional[str]) -> NotificationStatus:
        if not self.settings.resend_api_key:
            logger.info("email_simulated", to=to, subject=subject, reason="no RESEND_API_KEY")
            return NotificationStatus.SIMULATED
        if "@" not in (to or ""):
            logger.info("email_simulated", to=to, subject=subject, reason="no FLEET_MANAGER_EMAIL")
            return NotificationStatus.SIMULATED

        try:
            import resend
            resend.api_key = self.settings.resend_api_key
            payload = {
                "from": self.settings.resend_from_email,
                "to": [to],
                "subject": subject,
                "text": message,
            }
            if html:
                payload["html"] = html
            result = resend.Emails.send(payload)
            logger.info("email_sent", to=to, subject=subject, id=(result or {}).get("id"))
            return NotificationStatus.SENT
        except Exception as e:
            logger.error("email_failed", to=to, error=str(e)[:300])
            return NotificationStatus.FAILED

    # --- business notifications ------------------------------------------

    def notify_critical_incident(self, incident, vehicle: Vehicle, analysis: dict) -> list[Notification]:
        """CRITICAL/HIGH incidents: in-app + email to the fleet manager."""
        severity = analysis.get("severity", "HIGH")
        category = (analysis.get("category") or incident.category or "Issue").replace("_", " ").title()
        urgency = "requires IMMEDIATE attention" if severity == "CRITICAL" else "requires attention within 24–48h"
        subject = f"[{severity}] {vehicle.fleet_number} — {category} {urgency}"

        actions = analysis.get("recommended_actions") or []
        parts = analysis.get("required_parts") or []
        recalls = analysis.get("related_recalls") or []
        lines = [
            f"Vehicle: {vehicle.fleet_number} ({vehicle.year} {vehicle.make} {vehicle.model}, {vehicle.mileage:,} km)",
            f"Reported by: {incident.reported_by}",
            f"Report: {incident.description}",
            "",
            f"FleetPilot assessment ({severity} / {category}):",
            analysis.get("summary", ""),
        ]
        if actions:
            lines += ["", "Recommended actions:"] + [f"  {i + 1}. {a}" for i, a in enumerate(actions)]
        if parts:
            lines += ["", "Parts requested:"] + [f"  - {p.get('name')} ×{p.get('quantity', 1)}" for p in parts]
        if recalls:
            lines += ["", f"Related open NHTSA recall campaign(s): {', '.join(recalls)}"]
        lines += [
            "",
            f"Vehicle status: {analysis.get('vehicle_status', vehicle.status.value).replace('_', ' ')}",
            "A maintenance task is waiting for your approval in FleetPilot → Maintenance."
            if analysis.get("requires_manager_approval") else
            "A maintenance task has been scheduled in FleetPilot → Maintenance.",
        ]
        message = "\n".join(lines)
        html = _html_wrap(subject, message)

        return [
            self.send("Fleet Manager", NotificationChannel.IN_APP, subject, message, "incident", str(incident.id)),
            self.send("Fleet Manager", NotificationChannel.EMAIL, subject, message, "incident", str(incident.id), html=html),
        ]

    def notify_task_approved(self, task: MaintenanceTask, vehicle: Optional[Vehicle]) -> Notification:
        fleet_num = vehicle.fleet_number if vehicle else "Unknown"
        subject = f"Maintenance Task Approved — {fleet_num}"
        message = f"Task '{task.title}' has been approved and is now ready for the workshop to start."
        return self.send("Maintenance Team", NotificationChannel.IN_APP, subject, message, "maintenance_task", str(task.id))

    def notify_task_completed(self, task: MaintenanceTask, vehicle: Optional[Vehicle], vehicle_restored: bool) -> Notification:
        fleet_num = vehicle.fleet_number if vehicle else "Unknown"
        subject = f"Maintenance Completed — {fleet_num}"
        message = f"Task '{task.title}' was completed."
        if vehicle_restored:
            message += f" {fleet_num} has been returned to ACTIVE service."
        return self.send("Fleet Manager", NotificationChannel.IN_APP, subject, message, "maintenance_task", str(task.id))

    def send_digest(self, subject: str, digest: str) -> list[Notification]:
        """Daily fleet health digest — in-app + email."""
        return [
            self.send("Fleet Manager", NotificationChannel.IN_APP, subject, digest, "fleet_scan", None),
            self.send("Fleet Manager", NotificationChannel.EMAIL, subject, digest, "fleet_scan", None, html=_html_wrap(subject, digest)),
        ]

    def send_approval_reminder(self, tasks: list[tuple[MaintenanceTask, Optional[Vehicle]]], waiting_hours: int) -> list[Notification]:
        subject = f"[REMINDER] {len(tasks)} maintenance task(s) waiting for your approval"
        lines = [f"The following tasks have been waiting longer than {waiting_hours}h for approval:", ""]
        for task, vehicle in tasks:
            fleet = vehicle.fleet_number if vehicle else "?"
            lines.append(f"  - {fleet} · {task.severity.value} · {task.title} (created {task.created_at:%d %b %H:%M})")
        lines += ["", "Approve or reject them in FleetPilot → Maintenance."]
        message = "\n".join(lines)
        return [
            self.send("Fleet Manager", NotificationChannel.IN_APP, subject, message, "approval_reminder", None),
            self.send("Fleet Manager", NotificationChannel.EMAIL, subject, message, "approval_reminder", None, html=_html_wrap(subject, message)),
        ]


def _html_wrap(title: str, body: str) -> str:
    import html as _html
    return (
        "<div style=\"font-family:-apple-system,Segoe UI,Roboto,sans-serif;max-width:640px;margin:0 auto;color:#0f172a\">"
        "<div style=\"background:#0f172a;color:#fff;padding:14px 18px;border-radius:8px 8px 0 0;font-weight:600\">FleetPilot AI</div>"
        f"<div style=\"border:1px solid #e2e8f0;border-top:0;padding:18px;border-radius:0 0 8px 8px\">"
        f"<h2 style=\"margin:0 0 12px;font-size:16px\">{_html.escape(title)}</h2>"
        f"<pre style=\"white-space:pre-wrap;font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0\">{_html.escape(body)}</pre>"
        "</div></div>"
    )
