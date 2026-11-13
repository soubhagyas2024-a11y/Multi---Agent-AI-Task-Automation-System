"""LangGraph orchestration:

coordinator -> planner -> execute_layer <-> (loop) -> verify -> finalize -> memory
Conditional edges: execute_layer loops while subtasks are ready (parallel layers), ends early on
cancel / pause / approval / timeout; verify may send failed work back for one corrective round.
"""
from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, StateGraph

from agents.agent_state import AgentState
from workflows import nodes, routing


@lru_cache(maxsize=1)
def get_graph():
    g = StateGraph(AgentState)
    g.add_node("coordinator", nodes.coordinator_node)
    g.add_node("planner", nodes.planner_node)
    g.add_node("execute_layer", nodes.execute_layer_node)
    g.add_node("verify", nodes.verify_node)
    g.add_node("finalize", nodes.finalize_node)
    g.add_node("memory", nodes.memory_node)
    g.set_entry_point("coordinator")
    g.add_edge("coordinator", "planner")
    g.add_edge("planner", "execute_layer")
    g.add_conditional_edges("execute_layer", routing.after_layer, {"execute_layer": "execute_layer", "verify": "verify", "finalize": "finalize"})
    g.add_conditional_edges("verify", routing.after_verify, {"execute_layer": "execute_layer", "finalize": "finalize"})
    g.add_edge("finalize", "memory")
    g.add_edge("memory", END)
    return g.compile()
