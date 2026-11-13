"""Visual workflow definitions -> validated, executable subtask plans."""
from __future__ import annotations

import json
from typing import Any

from agents.agent_state import AGENT_CATALOG, WORKER_AGENTS, SubTask

DEFAULT_INSTRUCTION = {
    "researcher": "Research the topic of the workflow objective and report key findings with sources.",
    "data_analyst": "Analyse the attached dataset and report statistics, data quality and charts.",
    "coder": "Write the code needed for the workflow objective.",
    "writer": "Write a professional report combining the previous steps' outputs.",
    "executor": "Perform the file operations needed for the workflow objective.",
    "verifier": "Review the previous steps' outputs for completeness and accuracy.",
    "memory": "Save the key outcome of this workflow to memory.",
}


def validate(defn: dict) -> None:
    nodes = defn.get("nodes") or []
    if not 1 <= len(nodes) <= 12:
        raise ValueError("A workflow needs between 1 and 12 nodes")
    ids = [n["id"] for n in nodes]
    if len(set(ids)) != len(ids):
        raise ValueError("Node ids must be unique")
    for n in nodes:
        if n["agent"] not in WORKER_AGENTS:
            raise ValueError(f"Unknown or unsupported agent '{n['agent']}'")
        for d in n.get("depends_on", []):
            if d not in ids or d == n["id"]:
                raise ValueError(f"Node '{n['id']}' depends on invalid node '{d}'")
        c = n.get("condition")
        if c and c.get("source") not in ids:
            raise ValueError(f"Condition on '{n['id']}' references an unknown node")
    # cycle detection (Kahn)
    indeg = {n["id"]: len(n.get("depends_on", [])) for n in nodes}
    queue, seen = [i for i, d in indeg.items() if d == 0], 0
    while queue:
        cur = queue.pop()
        seen += 1
        for n in nodes:
            if cur in n.get("depends_on", []):
                indeg[n["id"]] -= 1
                if indeg[n["id"]] == 0:
                    queue.append(n["id"])
    if seen != len(nodes):
        raise ValueError("Workflow contains a cycle")


def normalize(defn: dict) -> dict:
    """Sequential workflows without explicit edges are chained in list order."""
    nodes = [dict(n) for n in defn["nodes"]]
    if defn.get("workflow_type", "sequential") == "sequential":
        for i, n in enumerate(nodes):
            if i and not n.get("depends_on"):
                n["depends_on"] = [nodes[i - 1]["id"]]
    return {**defn, "nodes": nodes}


def to_subtasks(defn: dict) -> list[SubTask]:
    defn = normalize(defn)
    validate(defn)
    return [{"id": n["id"], "agent": n["agent"], "description": (n.get("instruction") or "").strip() or DEFAULT_INSTRUCTION[n["agent"]],
             "depends_on": list(n.get("depends_on", [])), "status": "pending", "result": "", "attempts": 0,
             "requires_approval": False, "condition": n.get("condition"), "meta": {}} for n in defn["nodes"]]


def mode_for(workflow_type: str) -> str:
    return "sequential" if workflow_type == "sequential" else "parallel"


def dumps(defn: dict[str, Any]) -> str:
    return json.dumps(defn)


__all__ = ["validate", "normalize", "to_subtasks", "mode_for", "dumps", "AGENT_CATALOG"]
