"""APScheduler integration for scheduled / recurring tasks and workflows."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.database import session_scope
from backend.models import ScheduledTask, User, Workflow
from backend.services import task_service as ts
from utils.helpers import utcnow
from utils.logger import get_logger

logger = get_logger("scheduler")
scheduler = BackgroundScheduler(timezone="UTC")
_INTERVALS = {"hourly": {"hours": 1}, "daily": {"days": 1}, "weekly": {"weeks": 1}}


def _job_id(sid: int) -> str:
    return f"sched_{sid}"


def run_scheduled(sid: int) -> None:
    from automation.task_engine import engine

    try:
        with session_scope() as db:
            s = db.get(ScheduledTask, sid)
            if not s or s.status != "active":
                return
            user = db.get(User, s.user_id)
            if s.workflow_id and db.get(Workflow, s.workflow_id):
                t = ts.create_workflow_task(db, user, db.get(Workflow, s.workflow_id), scheduled_id=sid)
            else:
                t = ts.create_task(db, user, s.task_description, scheduled_id=sid)
            s.last_run = utcnow()
            if s.recurrence == "once":
                s.status = "completed"
            tid = t.id
        engine.submit(tid)
    except Exception:  # noqa: BLE001
        logger.exception("Scheduled job %s failed", sid)


def add_job(s: ScheduledTask) -> None:
    start = s.schedule_time.replace(tzinfo=timezone.utc)
    if s.recurrence == "once":
        if start <= datetime.now(timezone.utc):
            raise ValueError("Schedule time must be in the future (UTC)")
        trigger = DateTrigger(run_date=start)
    else:
        trigger = IntervalTrigger(start_date=start, **_INTERVALS[s.recurrence])
    scheduler.add_job(run_scheduled, trigger, args=[s.id], id=_job_id(s.id), replace_existing=True, misfire_grace_time=300)


def remove_job(sid: int) -> None:
    try:
        scheduler.remove_job(_job_id(sid))
    except Exception:  # noqa: BLE001
        pass


def next_run(sid: int) -> Optional[str]:
    j = scheduler.get_job(_job_id(sid))
    return j.next_run_time.astimezone(timezone.utc).replace(tzinfo=None).isoformat() if j and j.next_run_time else None


def start() -> None:
    if scheduler.running:
        return
    scheduler.start()
    with session_scope() as db:
        for s in db.query(ScheduledTask).filter_by(status="active"):
            try:
                add_job(s)
            except ValueError:
                s.status = "completed"
    logger.info("Scheduler started")


def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
