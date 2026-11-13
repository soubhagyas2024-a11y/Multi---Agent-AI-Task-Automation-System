"""Verification Agent: deterministic checks + LLM review of outputs."""
from __future__ import annotations

from pathlib import Path

from agents.agent_state import AgentState, SubTask, build_context
from integrations import gemini_client
from utils.helpers import truncate

NAME = "verifier"
SYSTEM = ("You are the Verification Agent. Review the agents' outputs against the user's objective. Flag ONLY clear problems: "
          "incomplete work, content that ignores the request, internal contradictions, claims not supported by the provided sources, "
          'or broken code. Be lenient on style. Reply ONLY with JSON: {"passed":true|false,"issues":["..."],"retry":["subtask ids"],'
          '"feedback":{"subtask id":"what to fix"}}.')


def verify(state: AgentState) -> dict:
    subs = state.get("subtasks", [])
    issues: list[str] = []
    retry: set[str] = set()
    feedback: dict[str, str] = {}
    for s in subs:
        if s["status"] in ("failed",):
            issues.append(f"{s['id']} ({s['agent']}) failed: {truncate(s.get('result'), 200)}")
            retry.add(s["id"])
        elif s["status"] == "done" and s["agent"] not in ("verifier", "memory") and not (s.get("result") or "").strip():
            issues.append(f"{s['id']} ({s['agent']}) produced no output")
            retry.add(s["id"])
    for a in state.get("artifacts", []):
        p = Path(a["path"])
        if not p.exists() or p.stat().st_size == 0:
            issues.append(f"Generated file missing or empty: {p.name}")
    llm_note = ""
    done = [s for s in subs if s["status"] == "done" and s["agent"] not in ("verifier", "memory")]
    if done and not retry and gemini_client.is_configured():
        body = "\n\n".join(f"[{s['id']}] {s['agent']} - task: {s['description']}\nOUTPUT:\n{truncate(s.get('result'), 2500)}" for s in done)
        try:
            data = gemini_client.generate_json(f"OBJECTIVE: {state.get('objective')}\n\n{body}", system=SYSTEM)
            ids = {s["id"] for s in done}
            if not data.get("passed", True):
                issues += [str(i) for i in data.get("issues", [])][:6]
                retry |= {r for r in data.get("retry", []) if r in ids}
                feedback = {k: str(v) for k, v in (data.get("feedback") or {}).items() if k in ids}
        except Exception as exc:  # noqa: BLE001 - review is best effort
            llm_note = f" (LLM review skipped: {type(exc).__name__})"
    return {"passed": not issues, "issues": issues, "retry": sorted(retry), "feedback": feedback,
            "summary": ("All checks passed" if not issues else f"{len(issues)} issue(s) found") + llm_note}


def run(state: AgentState, st: SubTask) -> dict:
    """Worker mode (used by visual workflows): review upstream outputs and return a report."""
    ctx = build_context(state, st)
    text = gemini_client.generate(f"{ctx}\n\nREVIEW TASK: {st['description']}\nGive a verdict (PASS/FAIL) and bullet-point findings.", system="You are the Verification Agent. Be precise and concise.")
    return {"output": text, "artifacts": []}
