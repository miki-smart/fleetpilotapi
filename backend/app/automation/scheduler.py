"""
In-process scheduler — makes the agent proactive even when no external scheduler
(Cloud Scheduler, GitHub Actions) is wired up. Runs the fleet health scan on a cron
schedule and, optionally, on a short interval for demos.
"""
from typing import Optional
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.session import SessionLocal
from app.automation.fleet_health_scan import run_fleet_health_scan

logger = get_logger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None


async def _scan_job(trigger: str) -> None:
    db = SessionLocal()
    try:
        result = await run_fleet_health_scan(db, triggered_by=trigger)
        logger.info("scheduled_scan_completed", trigger=trigger, tasks_created=result["tasks_created"], recalls=result["recalls_found"])
    except Exception as e:
        logger.error("scheduled_scan_failed", trigger=trigger, error=str(e)[:300])
    finally:
        db.close()


def start_scheduler() -> Optional[AsyncIOScheduler]:
    global _scheduler
    settings = get_settings()
    if not settings.scheduler_enabled:
        logger.info("scheduler_disabled")
        return None

    _scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)
    _scheduler.add_job(
        _scan_job,
        CronTrigger.from_crontab(settings.scan_schedule_cron, timezone=settings.scheduler_timezone),
        args=["scheduler:daily"],
        id="daily_fleet_health_scan",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    if settings.scan_interval_minutes > 0:
        _scheduler.add_job(
            _scan_job,
            IntervalTrigger(minutes=settings.scan_interval_minutes),
            args=["scheduler:interval"],
            id="interval_fleet_health_scan",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
    _scheduler.start()
    logger.info("scheduler_started", cron=settings.scan_schedule_cron, interval_minutes=settings.scan_interval_minutes, timezone=settings.scheduler_timezone)
    return _scheduler


def shutdown_scheduler() -> None:
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)


def scheduler_status() -> dict:
    settings = get_settings()
    jobs = []
    if _scheduler:
        for job in _scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "trigger": str(job.trigger),
                "next_run_at": job.next_run_time.isoformat() if job.next_run_time else None,
            })
    return {
        "enabled": settings.scheduler_enabled,
        "running": bool(_scheduler and _scheduler.running),
        "timezone": settings.scheduler_timezone,
        "cron": settings.scan_schedule_cron,
        "interval_minutes": settings.scan_interval_minutes,
        "external_token_configured": bool(settings.scheduler_token),
        "jobs": jobs,
    }
