import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from automation.task_engine import EngineBusy, engine
from backend import auth
from backend.database import get_db
from backend.models import Task, User, Workflow
from backend.schemas import WorkflowIn
from backend.services import task_service as ts
from utils.helpers import utcnow
from workflows import workflow_builder as wb

router = APIRouter(prefix="/workflow", tags=["workflow"])


def _out(w: Workflow) -> dict:
    d = json.loads(w.definition)
    return {"id": w.id, "name": w.name, "description": w.description, "workflow_type": w.workflow_type, "nodes": d.get("nodes", []),
            "created_at": w.created_at.isoformat(), "updated_at": w.updated_at.isoformat() if w.updated_at else None}


def _own(db: Session, user: User, wid: int) -> Workflow:
    w = db.get(Workflow, wid)
    if not w or w.user_id != user.id:
        raise HTTPException(404, "Workflow not found")
    return w


@router.post("/create", status_code=201)
def create(p: WorkflowIn, user: User = Depends(auth.rate_limited), db: Session = Depends(get_db)):
    defn = {"nodes": [n.model_dump() for n in p.nodes], "workflow_type": p.workflow_type}
    try:
        wb.validate(wb.normalize(defn))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    w = Workflow(user_id=user.id, name=p.name.strip(), description=p.description, workflow_type=p.workflow_type, definition=json.dumps(defn))
    db.add(w)
    db.commit()
    return _out(w)


@router.get("")
def list_workflows(user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return [_out(w) for w in db.query(Workflow).filter_by(user_id=user.id).order_by(Workflow.id.desc())]


@router.get("/{workflow_id}")
def get(workflow_id: int, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return _out(_own(db, user, workflow_id))


@router.put("/{workflow_id}")
def update(workflow_id: int, p: WorkflowIn, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    w = _own(db, user, workflow_id)
    defn = {"nodes": [n.model_dump() for n in p.nodes], "workflow_type": p.workflow_type}
    try:
        wb.validate(wb.normalize(defn))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    w.name, w.description, w.workflow_type, w.definition, w.updated_at = p.name.strip(), p.description, p.workflow_type, json.dumps(defn), utcnow()
    db.commit()
    return _out(w)


@router.delete("/{workflow_id}")
def delete(workflow_id: int, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    db.delete(_own(db, user, workflow_id))
    db.commit()
    return {"detail": "Workflow deleted"}


@router.post("/{workflow_id}/execute", status_code=201)
def execute(workflow_id: int, user: User = Depends(auth.rate_limited), db: Session = Depends(get_db)):
    w = _own(db, user, workflow_id)
    try:
        t = ts.create_workflow_task(db, user, w)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    try:
        engine.submit(t.id)
    except EngineBusy as exc:
        raise HTTPException(409, str(exc))
    db.refresh(t)
    return ts.task_to_dict(db, t)


@router.get("/{workflow_id}/history")
def history(workflow_id: int, user: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    _own(db, user, workflow_id)
    ts_ = db.query(Task).filter_by(workflow_id=workflow_id, user_id=user.id).order_by(Task.id.desc()).limit(30).all()
    return [ts.task_to_dict(db, t) for t in ts_]
