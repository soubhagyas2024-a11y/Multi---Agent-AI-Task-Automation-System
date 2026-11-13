from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from agents.agent_state import AGENT_TITLES, CORE_AGENTS
from backend import auth
from backend.database import get_db
from backend.models import Agent, User

router = APIRouter(prefix="/agents", tags=["agents"])


def agent_out(a: Agent) -> dict:
    return {"id": a.id, "agent_name": a.agent_name, "title": AGENT_TITLES.get(a.agent_name, a.agent_name), "description": a.description,
            "status": a.status, "enabled": a.status != "disabled", "core": a.agent_name in CORE_AGENTS, "tasks_completed": a.tasks_completed,
            "tasks_failed": a.tasks_failed, "success_rate": a.success_rate, "last_active": a.last_active.isoformat() if a.last_active else None}


def _get(db: Session, agent_id: int) -> Agent:
    a = db.get(Agent, agent_id)
    if not a:
        raise HTTPException(404, "Agent not found")
    return a


@router.get("")
def list_agents(_: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return [agent_out(a) for a in db.query(Agent).order_by(Agent.id)]


@router.get("/{agent_id}")
def get_agent(agent_id: int, _: User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return agent_out(_get(db, agent_id))


@router.post("/{agent_id}/enable")
def enable(agent_id: int, _: User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    a = _get(db, agent_id)
    a.status = "idle"
    db.commit()
    return agent_out(a)


@router.post("/{agent_id}/disable")
def disable(agent_id: int, _: User = Depends(auth.require_admin), db: Session = Depends(get_db)):
    a = _get(db, agent_id)
    if a.agent_name in CORE_AGENTS:
        raise HTTPException(400, "Core agents (coordinator, planner, verifier) cannot be disabled")
    a.status = "disabled"
    db.commit()
    return agent_out(a)
