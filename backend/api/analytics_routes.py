"""Analytics (all numbers come from the database) and admin endpoints."""
from collections import Counter, defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agents.agent_state import AGENT_TITLES
from automation.task_engine import engine
from backend import auth
from backend.api.auth_routes import user_out
from backend.config import settings
from backend.database import get_db
from backend.models import Agent, ExecutionLog, Subtask, Task, User
from integrations import gemini_client, tavily_client
from utils.helpers import utcnow

router = APIRouter(tags=["analytics"])
ACTIVE = ("pending", "running", "paused", "awaiting_approval")


def _scope(db: Session, user: User, all_: bool):
    q = db.query(Task)
    return q if (all_ and user.role == "admin") else q.filter(Task.user_id == user.id)


def _dur(t: Task):
    return (t.completed_at - t.started_at).total_seconds() if t.completed_at and t.started_at else None


@router.get("/analytics/overview")
def overview(all: bool = False, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    tasks = _scope(db, user, all).all()
    c = Counter(t.task_status for t in tasks)
    durs = [d for d in (_dur(t) for t in tasks if t.task_status == "completed") if d is not None]
    return {"total": len(tasks), "completed": c["completed"], "failed": c["failed"], "cancelled": c["cancelled"],
            "active": sum(c[s] for s in ACTIVE), "running": c["running"], "agents_total": db.query(Agent).count(),
            "agents_enabled": db.query(Agent).filter(Agent.status != "disabled").count(),
            "avg_seconds": round(sum(durs) / len(durs), 1) if durs else 0.0, "total_seconds": round(sum(durs), 1),
            "success_rate": round(100 * c["completed"] / (c["completed"] + c["failed"]), 1) if (c["completed"] + c["failed"]) else None}


@router.get("/analytics/tasks")
def task_analytics(all: bool = False, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    tasks = _scope(db, user, all).all()
    daily: dict = defaultdict(lambda: {"completed": 0, "failed": 0, "total": 0})
    for t in tasks:
        d = daily[t.created_at.date().isoformat()]
        d["total"] += 1
        if t.task_status in ("completed", "failed"):
            d[t.task_status] += 1
    return {"daily": [{"date": k, **v} for k, v in sorted(daily.items())], "status": dict(Counter(t.task_status for t in tasks)),
            "categories": dict(Counter(t.category or "general" for t in tasks)),
            "durations": [{"id": t.id, "seconds": round(d, 1), "category": t.category} for t in tasks if (d := _dur(t)) is not None]}


@router.get("/analytics/agents")
def agent_analytics(all: bool = False, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    ids = [t.id for t in _scope(db, user, all).with_entities(Task.id)]
    subs = db.query(Subtask).filter(Subtask.task_id.in_(ids or [0])).all() if ids else []
    per: dict = defaultdict(lambda: {"done": 0, "failed": 0, "total": 0})
    for s in subs:
        p = per[s.assigned_agent]
        p["total"] += 1
        if s.status in ("done", "failed"):
            p[s.status] += 1
    total = sum(p["total"] for p in per.values()) or 1
    out = []
    for a in db.query(Agent).order_by(Agent.id):
        p = per.get(a.agent_name, {"done": 0, "failed": 0, "total": 0})
        fin = p["done"] + p["failed"]
        out.append({"agent": a.agent_name, "title": AGENT_TITLES[a.agent_name], "status": a.status, "subtasks": p["total"], "completed": p["done"],
                    "failed": p["failed"], "success_rate": round(100 * p["done"] / fin, 1) if fin else None,
                    "utilisation": round(100 * p["total"] / total, 1), "avg_seconds": round(a.total_seconds / (a.tasks_completed + a.tasks_failed), 1) if (a.tasks_completed + a.tasks_failed) else 0})
    return out


@router.get("/analytics/activity")
def activity(limit: int = 40, all: bool = False, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    q = db.query(ExecutionLog)
    if not (all and user.role == "admin"):
        q = q.join(Task, Task.id == ExecutionLog.task_id).filter(Task.user_id == user.id)
    return [{"timestamp": g.timestamp.isoformat(), "task_id": g.task_id, "agent": g.agent_name, "action": g.action, "output": (g.output or "")[:300], "level": g.level}
            for g in q.order_by(ExecutionLog.id.desc()).limit(min(limit, 300))]


@router.get("/analytics/live")
def live(user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    running = _scope(db, user, False).filter(Task.task_status.in_(("running", "awaiting_approval", "paused"))).all()
    return {"running": [{"id": t.id, "description": t.task_description[:120], "status": t.task_status} for t in running],
            "busy_agents": [a.agent_name for a in db.query(Agent).filter_by(status="busy")], "engine_active": len(engine.active_ids())}


# ---------------- admin ----------------
@router.get("/admin/users")
def admin_users(_: User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    counts = Counter(t.user_id for t in db.query(Task.user_id))
    return [{**user_out(u), "tasks": counts[u.id]} for u in db.query(User).order_by(User.id)]


@router.post("/admin/users/{user_id}/toggle")
def admin_toggle_user(user_id: int, admin: User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == admin.id:
        raise HTTPException(400, "You cannot disable your own account")
    u.is_active = not u.is_active
    db.commit()
    return user_out(u)


@router.post("/admin/users/{user_id}/role")
def admin_set_role(user_id: int, role: str, admin: User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    if role not in ("admin", "user"):
        raise HTTPException(422, "role must be 'admin' or 'user'")
    u = db.get(User, user_id)
    if not u or u.id == admin.id:
        raise HTTPException(400, "Invalid target user")
    u.role = role
    db.commit()
    return user_out(u)


@router.get("/admin/logs")
def admin_logs(level: str | None = None, limit: int = 200, _: User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    q = db.query(ExecutionLog)
    if level:
        q = q.filter_by(level=level.upper())
    return [{"id": g.id, "timestamp": g.timestamp.isoformat(), "task_id": g.task_id, "agent": g.agent_name, "action": g.action, "output": (g.output or "")[:500], "level": g.level}
            for g in q.order_by(ExecutionLog.id.desc()).limit(min(limit, 1000))]


@router.get("/admin/usage")
def admin_usage(_: User = Depends(auth.require_admin)):
    return {"gemini": gemini_client.usage_stats(), "note": "Counters are per server process and reset on restart."}


@router.get("/admin/system")
def admin_system(_: User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    return {"gemini_configured": gemini_client.is_configured(), "tavily_configured": tavily_client.is_configured(), "gemini_model": settings.gemini_model,
            "max_retries": settings.max_retries, "task_timeout_seconds": settings.task_timeout_seconds, "max_upload_mb": settings.max_upload_mb,
            "scheduler_enabled": settings.scheduler_enabled, "users": db.query(User).count(), "tasks": db.query(Task).count(), "server_time_utc": utcnow().isoformat()}
