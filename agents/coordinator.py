"""Coordinator Agent: intent recognition, memory recall and final response composition."""
from __future__ import annotations

from agents import memory_agent
from agents.agent_state import AGENT_TITLES, AgentState
from integrations import gemini_client
from utils.helpers import detect_category, truncate

SYSTEM = ("You are the Coordinator Agent. Combine the specialist agents' results into ONE clear final answer for the user. "
          "Preserve concrete content (code, findings, source references). Mention generated files by name. If a verification issue "
          "remains or a subtask failed, say so honestly. Do not invent anything.")


def understand(state: AgentState) -> dict:
    mem = ""
    try:
        mem = memory_agent.recall(state["user_id"], state["instruction"])
    except Exception:  # noqa: BLE001 - memory must never block a task
        pass
    return {"category": detect_category(state["instruction"]), "memory_context": mem}


def _files_note(state: AgentState) -> str:
    arts = state.get("artifacts", [])
    return ("\n\n**Generated files:** " + ", ".join(a.get("filename", a["path"].split("/")[-1]) for a in arts)) if arts else ""


def compose_final(state: AgentState) -> str:
    subs = state.get("subtasks", [])
    done = [s for s in subs if s["status"] == "done" and s["agent"] not in ("verifier",)]
    failed = [s for s in subs if s["status"] in ("failed", "blocked")]
    note = ""
    if failed:
        note = "\n\n**Some steps failed:**\n" + "\n".join(f"- {AGENT_TITLES[s['agent']]} ({s['id']}): {truncate(s.get('result'), 200)}" for s in failed)
    issues = (state.get("verification") or {}).get("issues") or []
    if issues and not failed:
        note += "\n\n**Verification notes:** " + "; ".join(issues[:4])
    if not done:
        return "No steps completed successfully." + note
    if len(done) == 1:
        return done[0]["result"] + note + _files_note(state)
    body = "\n\n".join(f"### {AGENT_TITLES[s['agent']]} — {s['id']}\n{truncate(s['result'], 3500)}" for s in done)
    try:
        text = gemini_client.generate(f"OBJECTIVE: {state.get('objective')}\n\nRESULTS:\n{body}", system=SYSTEM, max_output_tokens=6000)
    except Exception:  # noqa: BLE001
        text = body
    return text + note + _files_note(state)


def partial_summary(state: AgentState) -> str:
    return "\n".join(f"- {s['id']} {AGENT_TITLES[s['agent']]}: {s['status']}" for s in state.get("subtasks", []))
