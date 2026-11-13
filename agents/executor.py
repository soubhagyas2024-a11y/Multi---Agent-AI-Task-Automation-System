"""Execution Agent: approved file operations in the user workspace and restricted Python runs.

Never runs shell commands. Sensitive actions raise ApprovalRequired until the user approves.
"""
from __future__ import annotations

from agents.agent_state import AgentError, AgentState, ApprovalRequired, SubTask, build_context
from automation import code_execution, file_automation as fa
from integrations import gemini_client

NAME = "executor"
SENSITIVE = {"delete", "organize", "run_python", "overwrite_text"}
SYSTEM = (
    "You are the Execution Agent. Convert the task into a JSON plan of at most 5 supported actions. Supported: "
    '{"action":"create_folder","path":""} {"action":"write_text","path":"","content":""} {"action":"overwrite_text","path":"","content":""} '
    '{"action":"write_csv","path":"","rows":[[...]]} {"action":"rename","path":"","new_path":""} {"action":"delete","path":""} '
    '{"action":"organize","path":"."} {"action":"list","path":"."} {"action":"run_python","code":""}. '
    "Paths are relative to the workspace. You CANNOT send emails, make purchases, publish or run shell commands - skip those. "
    'Reply ONLY with JSON: {"actions":[...]}.'
)


def _perform(ws, a: dict, state: AgentState) -> tuple[str, str | None]:
    act = a.get("action")
    p = str(a.get("path", "."))
    if act == "create_folder":
        return fa.create_folder(ws, p), None
    if act in ("write_text", "overwrite_text"):
        fa.write_text(ws, p, str(a.get("content", "")), overwrite=act == "overwrite_text")
        return f"Wrote {p}", p
    if act == "write_csv":
        rows = a.get("rows") or []
        if not isinstance(rows, list) or not all(isinstance(r, list) for r in rows):
            raise AgentError("write_csv needs rows as a list of lists")
        fa.write_csv(ws, p, rows)
        return f"Wrote {p} ({len(rows)} rows)", p
    if act == "rename":
        return fa.rename(ws, p, str(a.get("new_path", ""))), None
    if act == "delete":
        return fa.delete(ws, p), None
    if act == "organize":
        return fa.organize_by_extension(ws, p), None
    if act == "list":
        return fa.list_dir(ws, p), None
    if act == "run_python":
        r = code_execution.run_python(str(a.get("code", "")), ws)
        return f"Python exit={r['returncode']}\nSTDOUT:\n{r['stdout']}\nSTDERR:\n{r['stderr']}", None
    raise AgentError(f"Unsupported action: {act}")


def run(state: AgentState, st: SubTask) -> dict:
    meta = st.setdefault("meta", {})
    actions = meta.get("actions")
    if actions is None:  # keep the plan stable across approval/resume
        data = gemini_client.generate_json(f"{build_context(state, st)}\n\nTASK: {st['description']}", system=SYSTEM)
        actions = [a for a in (data.get("actions") or []) if isinstance(a, dict)][:5]
        meta["actions"] = actions
    if not actions:
        return {"output": "No supported automation actions were required (external actions such as email must be done manually).", "artifacts": []}
    risky = [a for a in actions if a.get("action") in SENSITIVE]
    if (risky or st.get("requires_approval")) and not meta.get("approved"):
        shown = [{k: (str(v)[:300]) for k, v in a.items()} for a in (risky or actions)]
        raise ApprovalRequired("Approval needed for: " + ", ".join(a.get("action", "?") for a in shown), shown)
    ws = fa.user_dir(state["user_id"], "workspace")
    log, arts = [], []
    for a in actions:
        try:
            msg, created = _perform(ws, a, state)
        except (PermissionError, FileExistsError, FileNotFoundError, ValueError) as exc:
            raise AgentError(f"{a.get('action')} failed: {exc}")
        log.append(f"✔ {msg}")
        if created:
            arts.append({"path": str(fa.safe_join(ws, created)), "type": created.rsplit(".", 1)[-1] if "." in created else "txt"})
    return {"output": "Execution log:\n" + "\n".join(log), "artifacts": arts}
