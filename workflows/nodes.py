"""LangGraph node functions. Each node reads/updates the shared AgentState."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

from agents import coder, coordinator, data_analyst, executor, memory_agent, planner, researcher, verifier, writer
from agents.agent_state import AGENT_TITLES, AgentState, ApprovalRequired, SubTask
from backend.config import settings
from backend.services import task_service as ts
from memory.memory_manager import short_term
from utils.helpers import control, log_event, truncate
from utils.logger import get_logger
from workflows.routing import condition_met, downstream, propagate, ready

logger = get_logger("nodes")
AGENTS = {"researcher": researcher, "data_analyst": data_analyst, "coder": coder, "writer": writer,
          "executor": executor, "verifier": verifier, "memory": memory_agent}


def coordinator_node(state: AgentState) -> dict:
    tid = state["task_id"]
    log_event(tid, "coordinator", "received", state["instruction"])
    upd = coordinator.understand(state) if not state.get("subtasks") else {}
    short_term.put(tid, "instruction", state["instruction"])
    if upd.get("memory_context"):
        log_event(tid, "memory", "recalled", upd["memory_context"])
    return upd


def planner_node(state: AgentState) -> dict:
    tid = state["task_id"]
    if state.get("subtasks"):  # pre-planned (visual workflow) or resumed run
        log_event(tid, "planner", "plan_loaded", f"{len(state['subtasks'])} subtask(s)")
        return {"objective": state.get("objective") or state["instruction"]}
    objective, subs, fallback = planner.plan(state)
    ts.persist_subtasks(tid, subs)
    ts.set_plan_meta(tid, objective=objective)
    log_event(tid, "planner", "plan_created", "\n".join(f"{s['id']} [{s['agent']}] <- {s['depends_on']}: {s['description']}" for s in subs),
              "WARN" if fallback else "INFO")
    return {"objective": objective, "subtasks": subs}


def _work(state: AgentState, st: SubTask) -> tuple[SubTask, list[dict]]:
    tid, agent = state["task_id"], st["agent"]
    module, started, arts, ok = AGENTS.get(agent), time.time(), [], False
    if module is None or not ts.agent_enabled(agent):
        st["status"], st["result"] = "failed", f"Agent '{agent}' is unavailable or disabled"
        log_event(tid, agent, "error", st["result"], "ERROR")
        return st, arts
    st["status"] = "running"
    ts.set_agent_busy(agent, True)
    log_event(tid, agent, "start", f"{st['id']}: {st['description']}")
    tries = 0
    try:
        while True:
            if control.is_cancelled(tid):
                st["status"], st["result"] = "skipped", "Cancelled"
                return st, arts
            st["attempts"] = st.get("attempts", 0) + 1
            tries += 1
            try:
                out = module.run(state, st)
                st["status"], st["result"], ok = "done", out["output"], True
                for a in out.get("artifacts", []):
                    arts.append(ts.register_file(tid, state["user_id"], a["path"], a["type"]))
                log_event(tid, agent, "done", truncate(out["output"], 500))
                break
            except ApprovalRequired as exc:
                st["status"], st["result"] = "awaiting_approval", str(exc)
                st.setdefault("meta", {})["pending_actions"] = exc.actions
                log_event(tid, agent, "approval_required", str(exc), "WARN")
                return st, arts
            except Exception as exc:  # noqa: BLE001 - controlled retry
                log_event(tid, agent, "error", f"attempt {tries}: {type(exc).__name__}: {exc}", "ERROR")
                if tries > state.get("max_retries", settings.max_retries):
                    st["status"], st["result"] = "failed", f"{type(exc).__name__}: {exc}"
                    break
                time.sleep(min(2 ** tries, 5))
    finally:
        ts.set_agent_busy(agent, False)
        if st["status"] in ("done", "failed"):
            ts.record_agent_result(agent, ok, time.time() - started)
    return st, arts


def execute_layer_node(state: AgentState) -> dict:
    tid = state["task_id"]
    if control.is_cancelled(tid):
        return {"status": "cancelled"}
    if control.is_paused(tid):
        return {"status": "paused"}
    if time.time() - state.get("started_at", time.time()) > settings.task_timeout_seconds:
        return {"status": "failed", "error": f"Task timed out after {settings.task_timeout_seconds}s"}
    subs = propagate(deepcopy(state["subtasks"]))
    results = dict(state.get("results", {}))
    batch = ready(subs)
    for s in list(batch):
        if not condition_met(s, results):
            s["status"], s["result"] = "skipped", "Condition not met"
            batch.remove(s)
    if state.get("mode") == "sequential":
        batch = batch[:1]
    artifacts = list(state.get("artifacts", []))
    snap = {**state, "subtasks": subs, "results": results}
    if len(batch) > 1:
        with ThreadPoolExecutor(max_workers=min(len(batch), 4)) as pool:
            outs = list(pool.map(lambda s: _work(snap, s), batch))
    else:
        outs = [_work(snap, s) for s in batch]
    for st, arts in outs:
        if st["status"] == "done":
            results[st["id"]] = st["result"]
        artifacts += arts
    ts.persist_subtasks(tid, subs)
    upd: dict = {"subtasks": subs, "results": results, "artifacts": artifacts}
    after = propagate(deepcopy(subs))
    if any(s["status"] == "awaiting_approval" for s in after) and not ready(after):
        upd["status"] = "awaiting_approval"
    return upd


def verify_node(state: AgentState) -> dict:
    tid = state["task_id"]
    subs = deepcopy(state["subtasks"])
    res = verifier.verify({**state, "subtasks": subs})
    log_event(tid, "verifier", "verified", res["summary"] + ("\n" + "\n".join(res["issues"]) if res["issues"] else ""), "INFO" if res["passed"] else "WARN")
    upd: dict = {"verification": res}
    rounds = state.get("verify_rounds", 0)
    if res["retry"] and rounds < settings.verify_rounds:
        ids = downstream(subs, set(res["retry"]))
        results = dict(state.get("results", {}))
        for s in subs:
            if s["id"] in ids:
                s["status"] = "pending"
                s["meta"] = {**s.get("meta", {}), "feedback": res["feedback"].get(s["id"]) or "; ".join(res["issues"])[:500]}
                results.pop(s["id"], None)
        ts.persist_subtasks(tid, subs)
        upd.update(subtasks=subs, results=results, verify_rounds=rounds + 1)
        log_event(tid, "verifier", "retry_requested", ", ".join(sorted(ids)), "WARN")
    return upd


def finalize_node(state: AgentState) -> dict:
    tid, status = state["task_id"], state.get("status", "running")
    subs = state["subtasks"]
    if status == "cancelled":
        for s in subs:
            if s["status"] in ("pending", "awaiting_approval"):
                s["status"], s["result"] = "skipped", "Cancelled"
        ts.persist_subtasks(tid, subs)
        final = coordinator.partial_summary(state)
    elif status in ("paused", "awaiting_approval"):
        final = coordinator.partial_summary(state)
    else:
        if status != "failed":
            status = "failed" if any(s["status"] in ("failed", "blocked") for s in subs) else "completed"
        final = coordinator.compose_final(state)
    ts.finish_task(tid, status, final, state.get("error", ""))
    log_event(tid, "coordinator", f"task_{status}", truncate(final, 300), "INFO" if status != "failed" else "ERROR")
    return {"status": status, "final_response": final}


def memory_node(state: AgentState) -> dict:
    try:
        if state.get("status") == "completed":
            memory_agent.remember_task(state)
    except Exception:  # noqa: BLE001
        logger.exception("Could not store task summary")
    if state.get("status") in ("completed", "failed", "cancelled"):
        short_term.clear(state["task_id"])
    return {}
