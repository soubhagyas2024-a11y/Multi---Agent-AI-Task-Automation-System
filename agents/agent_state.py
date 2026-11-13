"""Shared workflow state, agent catalogue and context builder used by every agent."""
from __future__ import annotations

from typing import Any, Optional, TypedDict

from utils.helpers import truncate

AGENT_CATALOG: dict[str, str] = {
    "coordinator": "Receives instructions, recalls memory, orchestrates execution and composes the final answer.",
    "planner": "Analyses the request, decomposes it into dependent subtasks and assigns agents.",
    "researcher": "Searches the web with Tavily, extracts findings and keeps source references.",
    "data_analyst": "Analyses CSV/Excel files with Pandas, finds missing values, computes statistics and Plotly charts.",
    "coder": "Generates, explains and debugs Python code and saves complete code files.",
    "writer": "Writes reports, emails and summaries and exports DOCX/PDF documents.",
    "executor": "Runs approved automation actions: workspace file operations and restricted Python scripts.",
    "verifier": "Reviews outputs, detects incomplete work, validates files and requests corrections.",
    "memory": "Stores and retrieves user preferences, facts and task summaries.",
}
AGENT_TITLES = {k: k.replace("_", " ").title() + " Agent" for k in AGENT_CATALOG}
CORE_AGENTS = {"coordinator", "planner", "verifier"}  # cannot be disabled
WORKER_AGENTS = ["researcher", "data_analyst", "coder", "writer", "executor", "verifier", "memory"]


class SubTask(TypedDict, total=False):
    id: str
    agent: str
    description: str
    depends_on: list[str]
    status: str  # pending|running|done|failed|blocked|skipped|awaiting_approval
    result: str
    attempts: int
    requires_approval: bool
    condition: Optional[dict]
    meta: dict


class AgentState(TypedDict, total=False):
    task_id: int
    user_id: int
    instruction: str
    files: list[dict]
    memory_context: str
    objective: str
    category: str
    mode: str  # parallel | sequential
    allowed_agents: list[str]
    subtasks: list[SubTask]
    results: dict[str, str]
    artifacts: list[dict]
    verify_rounds: int
    verification: dict
    status: str
    final_response: str
    error: str
    started_at: float
    max_retries: int


class AgentError(RuntimeError):
    """A recoverable agent failure (the engine may retry)."""


class ApprovalRequired(Exception):
    def __init__(self, message: str, actions: list[dict]):
        super().__init__(message)
        self.actions = actions


def build_context(state: AgentState, st: SubTask) -> str:
    """Shared task context: objective, memory, outputs of upstream agents, reviewer feedback."""
    by_id = {s["id"]: s for s in state.get("subtasks", [])}
    parts = [f"OVERALL OBJECTIVE: {state.get('objective') or state.get('instruction', '')}"]
    if state.get("memory_context"):
        parts.append("RELEVANT USER MEMORY:\n" + truncate(state["memory_context"], 1500))
    for dep in st.get("depends_on", []):
        d = by_id.get(dep)
        if d:
            parts.append(f"OUTPUT FROM {d['agent'].upper()} ({dep}):\n{truncate(state.get('results', {}).get(dep, ''), 6000)}")
    fb = (st.get("meta") or {}).get("feedback")
    if fb:
        parts.append(f"REVIEWER FEEDBACK TO ADDRESS: {fb}")
    return "\n\n".join(parts)
