import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from components import task_monitor as tm  # noqa: E402
from components.api_client import ApiError, api  # noqa: E402
from components.sidebar import header  # noqa: E402

header("Task History", "Every task with its agents, timings, status and final output.")
status = st.selectbox("Filter by status", ["all", "completed", "failed", "running", "awaiting_approval", "paused", "cancelled"])
try:
    tasks = api.get("/tasks?limit=200" + ("" if status == "all" else f"&status={status}"))
except ApiError as exc:
    st.error(str(exc))
    st.stop()
if not tasks:
    st.info("No tasks found.")
    st.stop()
df = pd.DataFrame([{"ID": t["id"], "Description": t["task_description"][:80], "Agents": ", ".join(t["agents"]), "Started": (t["started_at"] or "")[:19],
                    "Completed": (t["completed_at"] or "")[:19], "Status": t["task_status"]} for t in tasks])
st.dataframe(df, use_container_width=True, hide_index=True)
tid = st.selectbox("Open task", [t["id"] for t in tasks], format_func=lambda i: f"#{i} - " + next(t["task_description"][:70] for t in tasks if t["id"] == i))
try:
    task = api.get(f"/tasks/{tid}")
except ApiError as exc:
    st.error(str(exc))
    st.stop()
tm.render_task(task, interactive=True, key="hist")
if task["task_status"] not in ("running",) and st.button("🗑 Delete this task", key="del"):
    try:
        api.delete(f"/tasks/{tid}")
        st.rerun()
    except ApiError as exc:
        st.error(str(exc))
