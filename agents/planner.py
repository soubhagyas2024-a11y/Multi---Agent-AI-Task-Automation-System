"""Planner Agent: objective -> dependency-aware subtasks with agent assignment."""
from __future__ import annotations

from agents.agent_state import AGENT_CATALOG, AgentState, SubTask
from integrations import gemini_client
from utils.helpers import detect_category
from utils.logger import get_logger

logger = get_logger("planner")
MAX_SUBTASKS = 8
SYSTEM = ("You are the Planner Agent of a multi-agent system. Decompose the user's request into the FEWEST subtasks needed (max 8). "
          "Assign each to exactly one allowed agent. Subtasks without dependencies run in PARALLEL, so only add depends_on when a "
          "subtask truly needs another's output. A final writer subtask should combine results when several agents contribute. "
          "Set requires_approval=true for anything that deletes/moves files or runs scripts. Do not plan verification (automatic). "
          'Reply ONLY with JSON: {"objective":"...","subtasks":[{"id":"t1","agent":"...","description":"specific instruction",'
          '"depends_on":[],"requires_approval":false}]}')


def validate_plan(data: dict, allowed: list[str]) -> tuple[str, list[SubTask]]:
    raw = data.get("subtasks")
    if not isinstance(raw, list) or not raw:
        raise ValueError("Plan has no subtasks")
    subs: list[SubTask] = []
    seen: set[str] = set()
    for i, r in enumerate(raw[:MAX_SUBTASKS], 1):
        sid = str(r.get("id") or f"t{i}")
        if sid in seen or r.get("agent") not in allowed or not str(r.get("description", "")).strip():
            raise ValueError(f"Invalid subtask {sid}")
        subs.append({"id": sid, "agent": r["agent"], "description": str(r["description"]).strip(), "status": "pending",
                     "depends_on": [d for d in map(str, r.get("depends_on") or []) if d in seen],  # earlier ids only => acyclic
                     "attempts": 0, "result": "", "requires_approval": bool(r.get("requires_approval")), "condition": None, "meta": {}})
        seen.add(sid)
    return str(data.get("objective") or ""), subs


def heuristic_plan(instruction: str, files: list[dict], allowed: list[str]) -> tuple[str, list[SubTask]]:
    t = instruction.lower()
    picks = []
    rules = [("researcher", ("research", "search", "latest", "news", "sources", "find out")),
             ("data_analyst", ("csv", "excel", "dataset", "analy", "chart", "statistic")),
             ("coder", ("code", "python", "script", "debug", "function", "program")),
             ("executor", ("folder", "rename", "text file", "create file", "organi", "delete file")),
             ("memory", ("remember that", "save to memory"))]
    for agent, kws in rules:
        if agent in allowed and any(k in t for k in kws):
            picks.append(agent)
    if "data_analyst" in picks and not any(f["filename"].lower().endswith((".csv", ".xlsx", ".xls")) for f in files):
        picks.remove("data_analyst")
    needs_writer = "writer" in allowed and (not picks or len(picks) > 1 or any(k in t for k in ("report", "summar", "email", "document", "pdf", "docx")))
    subs: list[SubTask] = []
    for i, a in enumerate(picks, 1):
        subs.append({"id": f"t{i}", "agent": a, "description": instruction, "status": "pending", "depends_on": [], "attempts": 0,
                     "result": "", "requires_approval": False, "condition": None, "meta": {}})
    if needs_writer:
        subs.append({"id": f"t{len(subs) + 1}", "agent": "writer", "description": f"Write the final deliverable for: {instruction}",
                     "status": "pending", "depends_on": [s["id"] for s in subs], "attempts": 0, "result": "", "requires_approval": False,
                     "condition": None, "meta": {}})
    if not subs:
        subs.append({"id": "t1", "agent": allowed[0], "description": instruction, "status": "pending", "depends_on": [], "attempts": 0,
                     "result": "", "requires_approval": False, "condition": None, "meta": {}})
    return instruction, subs


def plan(state: AgentState) -> tuple[str, list[SubTask], bool]:
    """Return (objective, subtasks, used_fallback)."""
    allowed = state["allowed_agents"]
    files = state.get("files", [])
    catalog = "\n".join(f"- {a}: {AGENT_CATALOG[a]}" for a in allowed)
    prompt = (f"USER REQUEST: {state['instruction']}\nATTACHED FILES: {[f['filename'] for f in files] or 'none'}\n"
              f"USER MEMORY: {state.get('memory_context') or 'none'}\nALLOWED AGENTS:\n{catalog}")
    try:
        obj, subs = validate_plan(gemini_client.generate_json(prompt, system=SYSTEM), allowed)
        return obj or state["instruction"], subs, False
    except Exception as exc:  # noqa: BLE001 - fall back to deterministic planning
        logger.warning("LLM planning failed (%s); using heuristic plan", exc)
        obj, subs = heuristic_plan(state["instruction"], files, allowed)
        return obj, subs, True
