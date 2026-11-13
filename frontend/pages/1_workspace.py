"""AI Workspace (chat + file upload + live agent activity) and Task Automation (scheduling)."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import streamlit as st  # noqa: E402

from components import task_monitor as tm  # noqa: E402
from components.api_client import ApiError, api  # noqa: E402
from components.sidebar import header  # noqa: E402

VIEW = globals().get("VIEW") or "workspace"


def workspace() -> None:
    header("AI Workspace", "Describe what you need - the agents plan, collaborate, verify and deliver.")
    st.session_state.setdefault("convo", [])
    c1, c2 = st.columns([3, 1])
    with c2:
        st.caption("Sample tasks")
        for i, s in enumerate(tm.SAMPLES):
            if st.button(f"Try sample {i + 1}", key=f"sample{i}", use_container_width=True, help=s):
                st.session_state["ws_prompt"] = s
        st.button("🎙️ Voice input (coming soon)", disabled=True, use_container_width=True)
    with c1:
        with st.form("ws_form"):
            text = st.text_area("Instruction", key="ws_prompt", height=130, placeholder="e.g. Analyse the attached sales CSV and write a PDF summary report")
            files = st.file_uploader("Attach files (CSV, Excel, text, PDF, DOCX, .py)", accept_multiple_files=True)
            a, b = st.columns([1, 1])
            prio = a.selectbox("Priority", ["normal", "high", "low"])
            go = b.form_submit_button("🚀 Submit task", type="primary", use_container_width=True)
    if go:
        if len(text.strip()) < 3:
            st.warning("Please enter an instruction.")
        else:
            tid = tm.submit(text.strip(), files, priority=prio)
            if tid:
                st.session_state["active"] = tid
                st.session_state["convo"] = [x for x in st.session_state["convo"] if x != tid] + [tid]
    if st.session_state.get("active"):
        st.subheader("Live execution")
        tm.show_active("active")
    older = [t for t in st.session_state["convo"] if t != st.session_state.get("active")][-5:]
    if older:
        st.subheader("Conversation history")
        for tid in older:
            try:
                t = api.get(f"/tasks/{tid}")
            except ApiError:
                continue
            with st.chat_message("user"):
                st.write(t["task_description"])
            with st.chat_message("assistant"):
                st.markdown(tm.pill(t["task_status"]), unsafe_allow_html=True)
                st.markdown((t.get("result") or "")[:700])


def automation() -> None:
    header("Task Automation", "Schedule one-off or recurring tasks and workflows (times are UTC).")
    try:
        wfs = api.get("/workflow")
    except ApiError as exc:
        st.error(str(exc))
        return
    with st.form("sched"):
        kind = st.radio("Run", ["Task instruction", "Saved workflow"], horizontal=True)
        desc = st.text_area("Task instruction", height=90)
        wf = st.selectbox("Workflow", [None] + [w["id"] for w in wfs], format_func=lambda i: "-" if i is None else next(w["name"] for w in wfs if w["id"] == i))
        c1, c2, c3 = st.columns(3)
        d = c1.date_input("Date (UTC)", datetime.utcnow().date())
        t = c2.time_input("Time (UTC)", (datetime.utcnow() + timedelta(minutes=5)).time().replace(second=0, microsecond=0))
        rec = c3.selectbox("Recurrence", ["once", "hourly", "daily", "weekly"])
        if st.form_submit_button("Schedule", type="primary"):
            body = {"schedule_time": datetime.combine(d, t).isoformat(), "recurrence": rec}
            body.update({"workflow_id": wf} if kind == "Saved workflow" else {"description": desc})
            try:
                api.post("/tasks/schedule", body)
                st.success("Scheduled")
            except ApiError as exc:
                st.error(str(exc))
    st.subheader("Upcoming & history")
    for s in api.get("/tasks/schedule/list"):
        with st.expander(f"#{s['id']} · {s['recurrence']} · {s['status']} · next: {(s['next_run'] or '-')[:16]}"):
            st.write(s["task_description"] or f"Workflow #{s['workflow_id']}")
            st.caption(f"Last run: {s['last_run'] or 'never'}")
            for h in s["history"]:
                st.markdown(f"Task #{h['task_id']} {tm.pill(h['status'])} {h['created_at'][:19]}", unsafe_allow_html=True)
            if s["status"] == "active" and st.button("Cancel schedule", key=f"cs{s['id']}"):
                api.delete(f"/tasks/schedule/{s['id']}")
                st.rerun()


workspace() if VIEW == "workspace" else automation()
