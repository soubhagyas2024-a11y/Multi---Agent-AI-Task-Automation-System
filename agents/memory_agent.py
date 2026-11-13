"""Memory Agent: saves/retrieves preferences, facts and task summaries."""
from __future__ import annotations

from agents.agent_state import AgentError, AgentState, SubTask, build_context
from integrations import gemini_client
from memory.memory_manager import MemoryManager
from utils.helpers import truncate

NAME = "memory"
SYSTEM = ("You are the Memory Agent. Decide whether the user wants to SAVE something to memory or SEARCH memory. "
          'Reply ONLY with JSON: {"action":"save"|"search","content":"text to save or search query","category":"preference|fact|note"}.')


def recall(user_id: int, query: str, k: int = 5) -> str:
    return "\n".join(f"- [{m.memory_category}] {m.memory_content}" for m in MemoryManager.search(user_id, query, k))


def remember_task(state: AgentState) -> None:
    final = truncate(state.get("final_response", ""), 300).replace("\n", " ")
    MemoryManager.add(state["user_id"], f"Task: {truncate(state['instruction'], 160)} -> {final}", "summary")


def run(state: AgentState, st: SubTask) -> dict:
    data = gemini_client.generate_json(f"{build_context(state, st)}\n\nSUBTASK: {st['description']}", system=SYSTEM)
    action, content = data.get("action", "search"), str(data.get("content", "")).strip()
    if not content:
        raise AgentError("Memory agent got empty content")
    if action == "save":
        MemoryManager.add(state["user_id"], content, data.get("category", "note"))
        return {"output": f"Saved to memory: {content}", "artifacts": []}
    return {"output": recall(state["user_id"], content) or "No relevant memories found.", "artifacts": []}
