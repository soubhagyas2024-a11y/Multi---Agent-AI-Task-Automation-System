"""Task persistence and orchestration helpers shared by the API, engine and graph nodes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from agents.agent_state import AGENT_CATALOG, AgentState, SubTask
from backend.config import settings
from backend.database import session_scope
from backend.models import Agent, ExecutionLog, GeneratedFile, Subtask, Task, User
from utils.helpers import detect_category, utcnow

ACTIVE = ("pending", "running", "paused", "awaiting_approval")


# ---------- row <-> dict ----------
def _row_to_sub(r: Subtask) -> SubTask:
    meta = json.loads(r.meta or "{}")
    return {"id": r.key, "agent": r.assigned_agent, "description": r.description, "status": r.status, "result": r.result or "",
            "depends_on": json.loads(r.depends_on or "[]"), "attempts": r.attempts or 0,
            "requires_approval": bool(meta.pop("requires_approval", False)), "condition": meta.pop("condition", None), "meta": meta}


def _fill_row(r: Subtask, s: SubTask) -> None:
    meta = dict(s.get("meta") or {})
    meta["requires_approval"] = bool(s.get("requires_approval"))
    meta["condition"] = s.get("condition")
    r.assigned_agent, r.description, r.status = s["agent"], s["description"], s["status"]
    r.result, r.attempts = s.get("result", ""), s.get("attempts", 0)
    r.depends_on, r.meta = json.dumps(s.get("depends_on", [])), json.dumps(meta, default=str)


def persist_subtasks(task_id: int, subs: list[SubTask]) -> None:
    with session_scope() as db:
        rows = {r.key: r for r in db.query(Subtask).filter_by(task_id=task_id)}
        for s in subs:
            r = rows.get(s["id"])
            if r is None:
                r = Subtask(task_id=task_id, key=s["id"], assigned_agent=s["agent"], description=s["description"])
                db.add(r)
            _fill_row(r, s)


# ---------- creation ----------
def create_task(db: Session, user: User, description: str, priority: str = "normal", file_ids: Optional[list[int]] = None,
                agents: Optional[list[str]] = None, workflow_id: Optional[int] = None, scheduled_id: Optional[int] = None,
                subtasks: Optional[list[SubTask]] = None, mode: str = "parallel", objective: Optional[str] = None) -> Task:
    ids: list[int] = []
    if file_ids:
        ids = [f.id for f in db.query(GeneratedFile).filter(GeneratedFile.id.in_(file_ids), GeneratedFile.user_id == user.id)]
        if len(ids) != len(set(file_ids)):
            raise ValueError("One or more files were not found")
    meta = {"file_ids": ids, "agents": agents or [], "mode": mode, "objective": objective}
    t = Task(user_id=user.id, task_description=description.strip(), priority=priority, workflow_id=workflow_id, scheduled_id=scheduled_id,
             category=detect_category(description), plan_json=json.dumps(meta))
    db.add(t)
    db.flush()
    for s in subtasks or []:
        r = Subtask(task_id=t.id, key=s["id"], assigned_agent=s["agent"], description=s["description"])
        _fill_row(r, s)
        db.add(r)
    db.commit()
    return t


def reset_task(db: Session, t: Task) -> None:
    """Prepare a finished task to run again (workflow tasks keep their fixed plan)."""
    rows = db.query(Subtask).filter_by(task_id=t.id).all()
    for r in rows:
        if t.workflow_id:
            r.status, r.result, r.attempts = "pending", "", 0
        else:
            db.delete(r)
    t.task_status, t.result, t.error, t.completed_at = "pending", None, None, None
    db.commit()


# ---------- state building / status ----------
def build_initial_state(task_id: int) -> AgentState:
    with session_scope() as db:
        t = db.get(Task, task_id)
        meta = json.loads(t.plan_json or "{}")
        files = [{"id": f.id, "filename": f.filename, "path": f.file_path} for f in
                 db.query(GeneratedFile).filter(GeneratedFile.id.in_(meta.get("file_ids") or [0]), GeneratedFile.user_id == t.user_id)]
        subs = [_row_to_sub(r) for r in db.query(Subtask).filter_by(task_id=task_id).order_by(Subtask.id)]
        for s in subs:
            if s["status"] in ("running",):
                s["status"] = "pending"
        enabled = [a.agent_name for a in db.query(Agent).filter(Agent.status != "disabled")]
        pref = meta.get("agents") or []
        allowed = [a for a in (pref or ["researcher", "data_analyst", "coder", "writer", "executor", "memory"]) if a in enabled and a != "verifier"]
        arts = [{"id": f.id, "filename": f.filename, "path": f.file_path, "type": f.file_type}
                for f in db.query(GeneratedFile).filter_by(task_id=task_id, kind="generated")]
        return {"task_id": task_id, "user_id": t.user_id, "instruction": t.task_description, "files": files, "memory_context": "",
                "objective": meta.get("objective") or "", "category": t.category or "general", "mode": meta.get("mode", "parallel"),
                "allowed_agents": allowed or ["writer"], "subtasks": subs, "artifacts": arts, "verify_rounds": 0, "verification": {},
                "results": {s["id"]: s["result"] for s in subs if s["status"] == "done"}, "status": "running", "final_response": "",
                "error": "", "max_retries": settings.max_retries}


def set_plan_meta(task_id: int, **updates: Any) -> None:
    with session_scope() as db:
        t = db.get(Task, task_id)
        meta = json.loads(t.plan_json or "{}")
        meta.update(updates)
        t.plan_json = json.dumps(meta)


def set_task_status(task_id: int, status: str, **fields: Any) -> None:
    with session_scope() as db:
        t = db.get(Task, task_id)
        if t:
            t.task_status = status
            for k, v in fields.items():
                setattr(t, k, v)


def finish_task(task_id: int, status: str, result: str, error: str = "") -> None:
    terminal = status in ("completed", "failed", "cancelled")
    set_task_status(task_id, status, result=result, error=error or None, completed_at=utcnow() if terminal else None)


def recover_interrupted() -> int:
    with session_scope() as db:
        rows = db.query(Task).filter(Task.task_status == "running").all()
        for t in rows:
            t.task_status, t.error, t.completed_at = "failed", "Interrupted by a server restart", utcnow()
        return len(rows)


# ---------- agents ----------
def agent_enabled(name: str) -> bool:
    with session_scope() as db:
        a = db.query(Agent).filter_by(agent_name=name).first()
        return bool(a and a.status != "disabled")


def set_agent_busy(name: str, busy: bool) -> None:
    with session_scope() as db:
        a = db.query(Agent).filter_by(agent_name=name).first()
        if a and a.status != "disabled":
            a.status = "busy" if busy else "idle"
            a.last_active = utcnow()


def record_agent_result(name: str, ok: bool, seconds: float) -> None:
    with session_scope() as db:
        a = db.query(Agent).filter_by(agent_name=name).first()
        if not a:
            return
        if ok:
            a.tasks_completed = (a.tasks_completed or 0) + 1
        else:
            a.tasks_failed = (a.tasks_failed or 0) + 1
        total = a.tasks_completed + a.tasks_failed
        a.success_rate = round(100.0 * a.tasks_completed / total, 1) if total else 100.0
        a.total_seconds = (a.total_seconds or 0) + seconds
        a.last_active = utcnow()


# ---------- files ----------
def register_file(task_id: Optional[int], user_id: int, path: str, ftype: str, kind: str = "generated") -> dict:
    with session_scope() as db:
        f = GeneratedFile(task_id=task_id, user_id=user_id, filename=Path(path).name, file_path=str(path), file_type=ftype, kind=kind)
        db.add(f)
        db.flush()
        return {"id": f.id, "filename": f.filename, "path": f.file_path, "type": f.file_type}


def file_to_dict(f: GeneratedFile) -> dict:
    return {"id": f.id, "task_id": f.task_id, "filename": f.filename, "file_type": f.file_type, "kind": f.kind,
            "created_at": f.created_at.isoformat() if f.created_at else None}


# ---------- serialisation ----------
def task_to_dict(db: Session, t: Task, detail: bool = False, subs: Optional[list[Subtask]] = None) -> dict:
    subs = subs if subs is not None else db.query(Subtask).filter_by(task_id=t.id).order_by(Subtask.id).all()
    done = sum(s.status in ("done", "skipped") for s in subs)
    end = t.completed_at or (utcnow() if t.started_at and t.task_status == "running" else None)
    meta = json.loads(t.plan_json or "{}")
    d = {"id": t.id, "user_id": t.user_id, "task_description": t.task_description, "task_status": t.task_status, "priority": t.priority,
         "category": t.category, "created_at": t.created_at.isoformat(), "started_at": t.started_at.isoformat() if t.started_at else None,
         "completed_at": t.completed_at.isoformat() if t.completed_at else None,
         "duration_seconds": round((end - t.started_at).total_seconds(), 1) if end and t.started_at else None,
         "progress": round(done / len(subs), 2) if subs else 0.0, "agents": sorted({s.assigned_agent for s in subs}),
         "result": t.result, "error": t.error, "workflow_id": t.workflow_id, "scheduled_id": t.scheduled_id}
    if detail:
        d["objective"] = meta.get("objective")
        d["subtasks"] = []
        for s in subs:
            sub = _row_to_sub(s)
            d["subtasks"].append({"key": sub["id"], "agent": sub["agent"], "description": sub["description"], "status": sub["status"],
                                  "result": sub["result"], "depends_on": sub["depends_on"], "attempts": sub["attempts"],
                                  "pending_actions": sub["meta"].get("pending_actions") if sub["status"] == "awaiting_approval" else None})
        logs = db.query(ExecutionLog).filter_by(task_id=t.id).order_by(ExecutionLog.id.desc()).limit(200).all()[::-1]
        d["logs"] = [{"timestamp": g.timestamp.isoformat(), "agent": g.agent_name, "action": g.action, "output": g.output, "level": g.level} for g in logs]
        d["files"] = [file_to_dict(f) for f in db.query(GeneratedFile).filter_by(task_id=t.id, kind="generated")]
    return d


def delete_task(db: Session, t: Task) -> None:
    for f in db.query(GeneratedFile).filter_by(task_id=t.id, kind="generated"):
        try:
            p = Path(f.file_path).resolve()
            if settings.generated_dir in p.parents:
                p.unlink(missing_ok=True)
        except OSError:
            pass
        db.delete(f)
    db.query(ExecutionLog).filter_by(task_id=t.id).delete()
    db.query(Subtask).filter_by(task_id=t.id).delete()
    db.delete(t)
    db.commit()


def create_workflow_task(db: Session, user: User, wf, scheduled_id: Optional[int] = None) -> Task:
    from workflows import workflow_builder as wb

    defn = json.loads(wf.definition)
    defn["workflow_type"] = wf.workflow_type
    subs = wb.to_subtasks(defn)
    return create_task(db, user, f"[Workflow] {wf.name}: {wf.description or 'run'}", workflow_id=wf.id, scheduled_id=scheduled_id,
                       subtasks=subs, mode=wb.mode_for(wf.workflow_type), objective=f"{wf.name}. {wf.description}".strip())
