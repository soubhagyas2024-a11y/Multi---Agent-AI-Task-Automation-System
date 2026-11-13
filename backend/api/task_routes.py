from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from agents.agent_state import WORKER_AGENTS
from automation.task_engine import EngineBusy, engine
from backend import auth
from backend.database import get_db
from backend.models import GeneratedFile, ScheduledTask, Subtask, Task, User, Workflow
from backend.schemas import ApprovalIn, ScheduleIn, TaskCreate
from backend.services import file_service, scheduler
from backend.services import task_service as ts
from utils.helpers import log_event

router = APIRouter(prefix="/tasks", tags=["tasks"])
files_router = APIRouter(prefix="/files", tags=["files"])


def _owned(db: Session, user: User, task_id: int) -> Task:
    t = db.get(Task, task_id)
    if not t or (t.user_id != user.id and user.role != "admin"):
        raise HTTPException(404, "Task not found")
    return t


def _start(task_id: int) -> None:
    try:
        engine.submit(task_id)
    except EngineBusy as exc:
        raise HTTPException(409, str(exc))
    except PermissionError as exc:
        raise HTTPException(403, str(exc))


@router.post("/create", status_code=201)
def create_task(p: TaskCreate, user: User = Depends(auth.rate_limited), db: Session = Depends(get_db)):
    bad = [a for a in p.agents if a not in WORKER_AGENTS]
    if bad:
        raise HTTPException(400, f"Unknown agents: {bad}")
    try:
        t = ts.create_task(db, user, p.description, p.priority, p.file_ids, p.agents)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if p.execute:
        _start(t.id)
        db.refresh(t)
    return ts.task_to_dict(db, t)


@router.get("")
def list_tasks(status: str | None = None, limit: int = 50, all: bool = False, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    q = db.query(Task)
    if not (all and user.role == "admin"):
        q = q.filter(Task.user_id == user.id)
    if status:
        q = q.filter(Task.task_status == status)
    tasks = q.order_by(Task.id.desc()).limit(min(max(limit, 1), 500)).all()
    subs: dict[int, list] = {}
    for s in db.query(Subtask).filter(Subtask.task_id.in_([t.id for t in tasks] or [0])):
        subs.setdefault(s.task_id, []).append(s)
    return [ts.task_to_dict(db, t, subs=subs.get(t.id, [])) for t in tasks]


@router.post("/schedule", status_code=201)
def schedule_task(p: ScheduleIn, user: User = Depends(auth.rate_limited), db: Session = Depends(get_db)):
    if p.workflow_id:
        wf = db.get(Workflow, p.workflow_id)
        if not wf or wf.user_id != user.id:
            raise HTTPException(404, "Workflow not found")
    s = ScheduledTask(user_id=user.id, task_description=p.description.strip(), schedule_time=p.schedule_time.replace(tzinfo=None),
                      recurrence=p.recurrence, workflow_id=p.workflow_id)
    db.add(s)
    db.commit()
    try:
        scheduler.add_job(s)
    except ValueError as exc:
        db.delete(s)
        db.commit()
        raise HTTPException(400, str(exc))
    return _sched(db, s)


def _sched(db: Session, s: ScheduledTask) -> dict:
    runs = db.query(Task).filter_by(scheduled_id=s.id).order_by(Task.id.desc()).limit(10).all()
    return {"id": s.id, "task_description": s.task_description, "workflow_id": s.workflow_id, "schedule_time": s.schedule_time.isoformat(),
            "recurrence": s.recurrence, "status": s.status, "last_run": s.last_run.isoformat() if s.last_run else None,
            "next_run": scheduler.next_run(s.id), "history": [{"task_id": t.id, "status": t.task_status, "created_at": t.created_at.isoformat()} for t in runs]}


@router.get("/schedule/list")
def list_schedules(user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return [_sched(db, s) for s in db.query(ScheduledTask).filter_by(user_id=user.id).order_by(ScheduledTask.id.desc())]


@router.delete("/schedule/{sid}")
def cancel_schedule(sid: int, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    s = db.get(ScheduledTask, sid)
    if not s or s.user_id != user.id:
        raise HTTPException(404, "Schedule not found")
    scheduler.remove_job(sid)
    s.status = "cancelled"
    db.commit()
    return {"detail": "Schedule cancelled"}


@router.get("/{task_id}")
def get_task(task_id: int, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return ts.task_to_dict(db, _owned(db, user, task_id), detail=True)


@router.post("/{task_id}/execute")
def execute_task(task_id: int, user: User = Depends(auth.rate_limited), db: Session = Depends(get_db)):
    t = _owned(db, user, task_id)
    if t.task_status in ("running", "paused", "awaiting_approval"):
        raise HTTPException(409, f"Task is {t.task_status}; use resume/approve instead")
    if t.task_status != "pending":
        ts.reset_task(db, t)
    _start(t.id)
    db.refresh(t)
    return ts.task_to_dict(db, t)


@router.post("/{task_id}/cancel")
def cancel_task(task_id: int, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    t = _owned(db, user, task_id)
    if t.task_status in ("completed", "failed", "cancelled"):
        raise HTTPException(409, "Task already finished")
    engine.cancel(t.id)
    db.refresh(t)
    return {"detail": "Cancellation requested", "task_status": t.task_status}


@router.post("/{task_id}/pause")
def pause_task(task_id: int, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    t = _owned(db, user, task_id)
    try:
        engine.pause(t.id)
    except EngineBusy as exc:
        raise HTTPException(409, str(exc))
    return {"detail": "Pause requested - the task stops after the current step"}


@router.post("/{task_id}/resume")
def resume_task(task_id: int, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    t = _owned(db, user, task_id)
    if t.task_status != "paused":
        raise HTTPException(409, "Only paused tasks can be resumed")
    _start(t.id)
    return {"detail": "Resumed"}


@router.post("/{task_id}/approve")
def approve_task(task_id: int, p: ApprovalIn, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    t = _owned(db, user, task_id)
    if t.task_status != "awaiting_approval":
        raise HTTPException(409, "Task is not waiting for approval")
    if not p.approved:
        log_event(t.id, "user", "approval_rejected", "User rejected the pending action", "WARN")
        engine.cancel(t.id)
        return {"detail": "Rejected - task cancelled"}
    import json
    for r in db.query(Subtask).filter_by(task_id=t.id, status="awaiting_approval"):
        meta = json.loads(r.meta or "{}")
        meta["approved"] = True
        meta.pop("pending_actions", None)
        r.meta, r.status = json.dumps(meta), "pending"
    db.commit()
    log_event(t.id, "user", "approved", "User approved pending actions")
    _start(t.id)
    return {"detail": "Approved - task resumed"}


@router.delete("/{task_id}")
def delete_task(task_id: int, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    t = _owned(db, user, task_id)
    if engine.is_running(t.id):
        raise HTTPException(409, "Cancel the running task first")
    ts.delete_task(db, t)
    return {"detail": "Task deleted"}


# ---------------- files ----------------
@files_router.post("/upload", status_code=201)
def upload(file: UploadFile = File(...), user: User = Depends(auth.rate_limited), db: Session = Depends(get_db)):
    return ts.file_to_dict(file_service.save_upload(db, user, file))


@files_router.get("")
def list_files(kind: str | None = None, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    q = db.query(GeneratedFile).filter_by(user_id=user.id)
    if kind:
        q = q.filter_by(kind=kind)
    return [ts.file_to_dict(f) for f in q.order_by(GeneratedFile.id.desc()).limit(200)]


@files_router.get("/{file_id}/download")
def download(file_id: int, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    f, p = file_service.get_file_for_user(db, user, file_id)
    return FileResponse(p, filename=f.filename)
