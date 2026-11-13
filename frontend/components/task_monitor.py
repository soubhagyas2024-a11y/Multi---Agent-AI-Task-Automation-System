"""Task submission, live monitoring, approval controls and result display."""
from __future__ import annotations

import time

import streamlit as st
import streamlit.components.v1 as stc

from components.api_client import ApiError, api

TERMINAL = ("completed", "failed", "cancelled")
ICON = {"done": "✅", "running": "⏳", "pending": "⏸️", "failed": "❌", "blocked": "🚫", "skipped": "⏭️", "awaiting_approval": "🔐"}
SAMPLES = [
    "Research the latest developments in renewable energy storage and write a PDF report with sources.",
    "Write a Python script that reads a CSV file and prints the average of each numeric column, and explain it.",
    "Draft a professional email to my team announcing next week's planning meeting.",
    "Create a folder called 'project_notes' and a text file inside it with a meeting-notes template.",
]


def pill(status: str) -> str:
    return f'<span class="pill {status}">{status.replace("_", " ")}</span>'


def submit(description: str, uploads: list, agents: list[str] | None = None, priority: str = "normal") -> int | None:
    try:
        ids = [api.upload(u.name, u.getvalue())["id"] for u in uploads or []]
        return api.post("/tasks/create", {"description": description, "file_ids": ids, "agents": agents or [], "priority": priority})["id"]
    except ApiError as exc:
        st.error(str(exc))
        return None


def render_task(task: dict, interactive: bool = True, key: str = "t") -> None:
    tid, status = task["id"], task["task_status"]
    dur = f" · {task['duration_seconds']}s" if task.get("duration_seconds") is not None else ""
    st.markdown(f"**Task #{tid}** {pill(status)} <span style='color:#8a96b2'>{task.get('category', '')}{dur}</span>", unsafe_allow_html=True)
    st.progress(min(task.get("progress", 0.0), 1.0))
    if task.get("objective"):
        st.caption(f"Objective: {task['objective']}")
    for s in task.get("subtasks", []):
        st.markdown(f'<div class="af-step">{ICON.get(s["status"], "•")} <b>{s["agent"].replace("_", " ").title()}</b> <span style="color:#8a96b2">({s["key"]}'
                    f'{" ← " + ", ".join(s["depends_on"]) if s["depends_on"] else ""})</span> {pill(s["status"])}<br>'
                    f'<span style="font-size:.85rem;color:#b6c0d8">{s["description"][:220]}</span></div>', unsafe_allow_html=True)
        if s["status"] == "awaiting_approval" and s.get("pending_actions"):
            st.warning("Approval needed for these actions:")
            st.json(s["pending_actions"])
    if interactive:
        _controls(task, status, key)
    if task.get("error") and status == "failed":
        st.error(task["error"])
    if status == "completed" or (status == "failed" and task.get("result")):
        with st.container(border=True):
            st.markdown(task["result"] or "_No output_")
    for f in task.get("files", []) if interactive else []:
        try:
            data = api.download(f["id"])
        except ApiError:
            continue
        c1, c2 = st.columns([1, 4])
        c1.download_button(f"⬇ {f['filename']}", data, file_name=f["filename"], key=f"{key}_dl_{f['id']}")
        if f["file_type"] == "html":
            with st.expander(f"Preview {f['filename']}"):
                stc.html(data.decode("utf-8", "replace"), height=420, scrolling=True)
    if interactive and task.get("logs"):
        with st.expander(f"Execution logs ({len(task['logs'])})"):
            for g in task["logs"]:
                st.text(f"{g['timestamp'][11:19]} [{g['level']}] {g['agent']}/{g['action']}: {g['output'][:300]}")


def _controls(task: dict, status: str, key: str) -> None:
    tid = task["id"]
    cols = st.columns(4)

    def act(label, path, body=None, kind="secondary", col=0):
        if cols[col].button(label, key=f"{key}_{path}_{tid}", type=kind, use_container_width=True):
            try:
                api.post(path, body) if body is not None else api.post(path)
                st.rerun()
            except ApiError as exc:
                st.error(str(exc))

    if status == "awaiting_approval":
        act("✅ Approve & continue", f"/tasks/{tid}/approve", {"approved": True}, "primary", 0)
        act("🚫 Reject", f"/tasks/{tid}/approve", {"approved": False}, "secondary", 1)
    elif status == "running":
        act("⏸ Pause", f"/tasks/{tid}/pause", None, "secondary", 0)
        act("✖ Cancel", f"/tasks/{tid}/cancel", None, "secondary", 1)
    elif status == "paused":
        act("▶ Resume", f"/tasks/{tid}/resume", None, "primary", 0)
        act("✖ Cancel", f"/tasks/{tid}/cancel", None, "secondary", 1)
    elif status in ("failed", "cancelled"):
        act("🔁 Retry", f"/tasks/{tid}/execute", None, "primary", 0)


def watch(task_id: int, key: str = "active", max_seconds: int = 900) -> None:
    """Poll a running task, rendering read-only progress, then show the interactive final view."""
    box, end = st.empty(), time.time() + max_seconds
    task = api.get(f"/tasks/{task_id}")
    while task["task_status"] in ("pending", "running") and time.time() < end:
        with box.container():
            render_task(task, interactive=False)
        time.sleep(1.5)
        task = api.get(f"/tasks/{task_id}")
    box.empty()
    render_task(task, interactive=True, key=key)


def show_active(state_key: str) -> None:
    tid = st.session_state.get(state_key)
    if not tid:
        return
    try:
        watch(tid, key=state_key)
    except ApiError as exc:
        st.error(str(exc))


def preset_form(state_key: str, label: str, placeholder: str, agents: list[str], upload_types: list[str] | None = None, multi: bool = False, button: str = "Run") -> None:
    with st.form(f"form_{state_key}"):
        text = st.text_area(label, placeholder=placeholder, height=120)
        files = st.file_uploader("Attach file(s)", type=upload_types, accept_multiple_files=True) if upload_types else []
        go = st.form_submit_button(button, type="primary")
    if go:
        if len(text.strip()) < 3:
            st.warning("Please enter an instruction.")
        else:
            st.session_state[state_key] = submit(text.strip(), files, agents)
    show_active(state_key)
