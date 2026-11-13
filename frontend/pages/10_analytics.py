import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from components import dashboard as d  # noqa: E402
from components.api_client import ApiError, api  # noqa: E402
from components.sidebar import current_user, header  # noqa: E402

header("Analytics", "Computed from real task, subtask and log records.")
admin = current_user()["role"] == "admin"
q = "?all=true" if admin and st.toggle("Include all users", value=False) else ""
try:
    ov, tk, ag = api.get(f"/analytics/overview{q}"), api.get(f"/analytics/tasks{q}"), api.get(f"/analytics/agents{q}")
except ApiError as exc:
    st.error(str(exc))
    st.stop()
cols = st.columns(5)
for c, (l, v) in zip(cols, [("Total", ov["total"]), ("Successful", ov["completed"]), ("Failed", ov["failed"]), ("Running", ov["running"]), ("Avg time", f"{ov['avg_seconds']}s")]):
    with c:
        d.metric_card(l, v)
st.caption(f"Total execution time: {ov['total_seconds']}s · Success rate: {ov['success_rate'] if ov['success_rate'] is not None else 'n/a'}%")
tabs = st.tabs(["Tasks", "Agents", "Live monitoring"] + (["Admin"] if admin else []))
with tabs[0]:
    d.daily_chart(tk["daily"])
    a, b, c = st.columns(3)
    with a:
        d.status_chart(tk["status"])
    with b:
        d.category_chart(tk["categories"])
    with c:
        d.duration_chart(tk["durations"])
with tabs[1]:
    a, b = st.columns(2)
    with a:
        d.agent_chart(ag)
    with b:
        d.utilisation_chart(ag)
    st.dataframe(pd.DataFrame(ag), use_container_width=True, hide_index=True)
with tabs[2]:
    live = api.get("/analytics/live")
    st.write(f"**Running tasks:** {len(live['running'])} · **Busy agents:** {', '.join(live['busy_agents']) or 'none'}")
    d.timeline(api.get(f"/analytics/activity?limit=30{q.replace('?', '&')}"), 30)
    if st.button("Refresh"):
        st.rerun()
if admin:
    with tabs[3]:
        u, l, s = st.tabs(["Users", "Execution logs", "API usage & system"])
        with u:
            for x in api.get("/admin/users"):
                c1, c2, c3 = st.columns([3, 2, 1])
                c1.write(f"**{x['username']}** ({x['email']})")
                c2.write(f"{x['role']} · {x['tasks']} tasks · {'active' if x['is_active'] else 'disabled'}")
                if x["id"] != current_user()["id"] and c3.button("Toggle", key=f"u{x['id']}"):
                    api.post(f"/admin/users/{x['id']}/toggle")
                    st.rerun()
        with l:
            lvl = st.selectbox("Level", ["", "INFO", "WARN", "ERROR"])
            st.dataframe(pd.DataFrame(api.get("/admin/logs" + (f"?level={lvl}" if lvl else ""))), use_container_width=True, hide_index=True)
        with s:
            st.json(api.get("/admin/usage"))
            st.json(api.get("/admin/system"))
