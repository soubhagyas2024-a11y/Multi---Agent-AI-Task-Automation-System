"""AgentFlow AI - Streamlit entry point.   Run from the project root:  streamlit run frontend/app.py"""
import runpy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import streamlit as st  # noqa: E402

from components import dashboard  # noqa: E402
from components.api_client import ApiError, api  # noqa: E402
from components.sidebar import current_user, header, setup_page  # noqa: E402
from components.task_monitor import pill  # noqa: E402

setup_page()


def overview() -> None:
    user = current_user()
    header("Overview", "Live status of your multi-agent workspace")
    all_ = user["role"] == "admin" and st.toggle("Show all users (admin)", value=False)
    q = "?all=true" if all_ else ""
    try:
        ov, tk, ag = api.get(f"/analytics/overview{q}"), api.get(f"/analytics/tasks{q}"), api.get(f"/analytics/agents{q}")
        recent, act = api.get(f"/tasks?limit=8{'&all=true' if all_ else ''}"), api.get(f"/analytics/activity?limit=12{'&all=true' if all_ else ''}")
    except ApiError as exc:
        st.error(str(exc))
        return
    cols = st.columns(5)
    for c, (l, v, s) in zip(cols, [("Tasks completed", ov["completed"], f"of {ov['total']} total"), ("Active tasks", ov["active"], "running / waiting"),
                                  ("Failed tasks", ov["failed"], "need attention"), ("AI agents", ov["agents_total"], f"{ov['agents_enabled']} enabled"),
                                  ("Avg completion", f"{ov['avg_seconds']}s", "completed tasks")]):
        with c:
            dashboard.metric_card(l, v, s)
    st.write("")
    a, b = st.columns(2)
    with a:
        dashboard.daily_chart(tk["daily"])
    with b:
        dashboard.agent_chart(ag)
    a, b = st.columns([3, 2])
    with a:
        st.subheader("Recent activity")
        if not recent:
            st.info("No tasks yet - open **AI Workspace** and try a sample task.")
        for t in recent:
            st.markdown(f"{pill(t['task_status'])} **#{t['id']}** {t['task_description'][:90]}", unsafe_allow_html=True)
    with b:
        st.subheader("System activity")
        dashboard.timeline(act)


def page(file: str, view: str | None = None):
    def _run():
        runpy.run_path(str(HERE / "pages" / file), run_name="__page__", init_globals={"VIEW": view})
    return _run


nav = st.navigation([
    st.Page(overview, title="Overview", icon="🏠", url_path="overview", default=True),
    st.Page(page("1_workspace.py", "workspace"), title="AI Workspace", icon="💬", url_path="workspace"),
    st.Page(page("2_agents.py"), title="Agent Management", icon="🤖", url_path="agents"),
    st.Page(page("1_workspace.py", "automation"), title="Task Automation", icon="⏰", url_path="automation"),
    st.Page(page("3_workflows.py"), title="Workflow Builder", icon="🔀", url_path="workflows"),
    st.Page(page("4_research.py"), title="Research Centre", icon="🔎", url_path="research"),
    st.Page(page("5_data_analysis.py"), title="Data Analysis", icon="📊", url_path="data"),
    st.Page(page("6_code_assistant.py"), title="Code Assistant", icon="💻", url_path="code"),
    st.Page(page("7_documents.py"), title="Document Generator", icon="📄", url_path="documents"),
    st.Page(page("8_task_history.py"), title="Task History", icon="🕘", url_path="history"),
    st.Page(page("9_memory.py"), title="AI Memory", icon="🧠", url_path="memory"),
    st.Page(page("10_analytics.py"), title="Analytics", icon="📈", url_path="analytics"),
    st.Page(page("11_settings.py"), title="Settings", icon="⚙️", url_path="settings"),
])
nav.run()
