"""Pure routing/dependency helpers for the LangGraph workflow (no I/O)."""
from __future__ import annotations

from copy import deepcopy

from agents.agent_state import AgentState, SubTask

TERMINAL = {"cancelled", "paused", "failed", "awaiting_approval"}


def propagate(subs: list[SubTask]) -> list[SubTask]:
    """Block/skip pending subtasks whose upstream failed or was skipped."""
    by = {s["id"]: s for s in subs}
    changed = True
    while changed:
        changed = False
        for s in subs:
            if s["status"] != "pending":
                continue
            ds = [by[d]["status"] for d in s["depends_on"] if d in by]
            if any(x in ("failed", "blocked") for x in ds):
                s["status"], changed = "blocked", True
            elif any(x == "skipped" for x in ds):
                s["status"], s["result"], changed = "skipped", "Skipped (upstream step skipped)", True
    return subs


def ready(subs: list[SubTask]) -> list[SubTask]:
    by = {s["id"]: s for s in subs}
    return [s for s in subs if s["status"] == "pending" and all(by[d]["status"] == "done" for d in s["depends_on"] if d in by)]


def condition_met(s: SubTask, results: dict[str, str]) -> bool:
    c = s.get("condition")
    if not c:
        return True
    hit = str(c.get("contains", "")).lower() in (results.get(c.get("source", ""), "") or "").lower()
    return hit != bool(c.get("negate"))


def downstream(subs: list[SubTask], ids: set[str]) -> set[str]:
    out = set(ids)
    changed = True
    while changed:
        changed = False
        for s in subs:
            if s["id"] not in out and any(d in out for d in s["depends_on"]):
                out.add(s["id"])
                changed = True
    return out


def after_layer(state: AgentState) -> str:
    if state.get("status") in TERMINAL:
        return "finalize"
    return "execute_layer" if ready(propagate(deepcopy(state["subtasks"]))) else "verify"


def after_verify(state: AgentState) -> str:
    return "execute_layer" if ready(propagate(deepcopy(state["subtasks"]))) else "finalize"
