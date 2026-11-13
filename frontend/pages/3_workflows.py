"""Visual workflow builder: add agent nodes, connect them, save, execute, pause/resume, view history."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402

from components import task_monitor as tm  # noqa: E402
from components.api_client import ApiError, api  # noqa: E402
from components.sidebar import header  # noqa: E402

AGENTS = ["researcher", "data_analyst", "coder", "writer", "executor", "verifier", "memory"]
COLORS = {"done": "#34d399", "running": "#60a5fa", "failed": "#f87171", "blocked": "#f87171", "skipped": "#6b7280", "awaiting_approval": "#fbbf24", "pending": "#8b5cf6"}

header("Workflow Builder", "Connect agents into sequential, parallel, conditional or scheduled workflows - saved and executed through LangGraph.")
ss = st.session_state
ss.setdefault("wf_nodes", [])
ss.setdefault("wf_id", None)


def levels(nodes):
    lv = {}
    for n in nodes:
        lv[n["id"]] = 0
    for _ in nodes:
        for n in nodes:
            for d in n.get("depends_on", []):
                if d in lv:
                    lv[n["id"]] = max(lv[n["id"]], lv[d] + 1)
    return lv


def effective(nodes, wtype):
    out = [dict(n) for n in nodes]
    if wtype == "sequential":
        for i, n in enumerate(out):
            if i and not n["depends_on"]:
                n["depends_on"] = [out[i - 1]["id"]]
    return out


def draw(nodes, statuses=None, outputs=None):
    if not nodes:
        st.info("Add your first node below. Example: researcher → data_analyst → writer → verifier.")
        return
    lv, rows, pos = levels(nodes), {}, {}
    for n in nodes:
        r = rows.get(lv[n["id"]], 0)
        rows[lv[n["id"]]] = r + 1
        pos[n["id"]] = (lv[n["id"]] * 2.2, -r * 1.4)
    fig = go.Figure()
    for n in nodes:
        for d in n["depends_on"]:
            if d in pos:
                (x0, y0), (x1, y1) = pos[d], pos[n["id"]]
                fig.add_annotation(x=x1 - .55, y=y1, ax=x0 + .55, ay=y0, xref="x", yref="y", axref="x", ayref="y", showarrow=True, arrowhead=3, arrowcolor="#4f8cff", arrowwidth=2)
        if n.get("condition"):
            fig.add_annotation(x=pos[n["id"]][0], y=pos[n["id"]][1] + .55, text="⚑ conditional", showarrow=False, font=dict(color="#fbbf24", size=10))
    st_ = statuses or {}
    fig.add_trace(go.Scatter(
        x=[pos[n["id"]][0] for n in nodes], y=[pos[n["id"]][1] for n in nodes], mode="markers+text", textposition="middle center",
        text=[f"<b>{n['agent']}</b><br>{n['id']}<br>{st_.get(n['id'], 'pending')}" for n in nodes],
        marker=dict(symbol="square", size=70, color=[COLORS.get(st_.get(n["id"], "pending"), "#8b5cf6") for n in nodes], line=dict(color="#4f8cff", width=1)),
        hovertext=[f"<b>{n['agent']}</b><br>Input: {n.get('instruction') or '(default)'}<br>Output: {((outputs or {}).get(n['id']) or '-')[:200]}" for n in nodes],
        hoverinfo="text", textfont=dict(color="white", size=11)))
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=130 + 110 * max(rows.values()),
                      xaxis=dict(visible=False, range=[-1, max(lv.values()) * 2.2 + 1]), yaxis=dict(visible=False), margin=dict(l=0, r=0, t=10, b=0), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)


try:
    saved = api.get("/workflow")
except ApiError as exc:
    st.error(str(exc))
    st.stop()

left, right = st.columns([2, 1])
with right:
    st.subheader("Saved workflows")
    if not saved:
        st.caption("Nothing saved yet.")
    for w in saved:
        c1, c2 = st.columns([3, 1])
        c1.write(f"**{w['name']}**  \n`{w['workflow_type']}` · {len(w['nodes'])} nodes")
        if c2.button("Load", key=f"ld{w['id']}"):
            ss.update(wf_nodes=[{"id": n["id"], "agent": n["agent"], "instruction": n["instruction"], "depends_on": n["depends_on"], "condition": n["condition"]} for n in w["nodes"]],
                      wf_id=w["id"], wf_name=w["name"], wf_desc=w["description"], wf_type=w["workflow_type"])
            st.rerun()
    if st.button("➕ Template: Research → Analysis → Report → Verify"):
        ss.update(wf_nodes=[
            {"id": "research", "agent": "researcher", "instruction": "Research the workflow topic", "depends_on": [], "condition": None},
            {"id": "report", "agent": "writer", "instruction": "Write a PDF report from the research", "depends_on": ["research"], "condition": None},
            {"id": "verify", "agent": "verifier", "instruction": "Review the report for accuracy and completeness", "depends_on": ["report"], "condition": None}],
            wf_id=None, wf_name="Research report", wf_desc="AI research topic", wf_type="sequential")
        st.rerun()

with left:
    c1, c2 = st.columns([2, 1])
    name = c1.text_input("Workflow name", key="wf_name")
    wtype = c2.selectbox("Type", ["sequential", "parallel", "conditional", "scheduled"], key="wf_type")
    desc = st.text_input("Objective / topic (used as shared context for all agents)", key="wf_desc")
    nodes = ss["wf_nodes"]
    draw(effective(nodes, wtype))
    with st.form("addnode", clear_on_submit=True):
        a, b = st.columns([1, 1])
        nid = a.text_input("Node id", placeholder="e.g. research")
        agent = b.selectbox("Agent", AGENTS)
        instr = st.text_area("Instruction for this agent (optional)", height=70)
        deps = st.multiselect("Runs after (connect to)", [n["id"] for n in nodes])
        cc1, cc2, cc3 = st.columns(3)
        csrc = cc1.selectbox("Only run if output of…", [""] + [n["id"] for n in nodes])
        ctext = cc2.text_input("…contains text")
        cneg = cc3.checkbox("negate (does NOT contain)")
        if st.form_submit_button("Add node", type="primary"):
            if not nid.strip() or nid in [n["id"] for n in nodes]:
                st.error("Node id must be non-empty and unique.")
            else:
                nodes.append({"id": nid.strip(), "agent": agent, "instruction": instr, "depends_on": deps,
                              "condition": {"source": csrc, "contains": ctext, "negate": cneg} if csrc and ctext else None})
                st.rerun()
    if nodes:
        rm = st.selectbox("Remove node", [""] + [n["id"] for n in nodes])
        if rm and st.button("Remove"):
            ss["wf_nodes"] = [{**n, "depends_on": [d for d in n["depends_on"] if d != rm]} for n in nodes if n["id"] != rm]
            st.rerun()
    sc = None
    if wtype == "scheduled":
        s1, s2, s3 = st.columns(3)
        sd = s1.date_input("Date (UTC)", datetime.utcnow().date())
        stime = s2.time_input("Time (UTC)", (datetime.utcnow() + timedelta(minutes=5)).time().replace(second=0, microsecond=0))
        srec = s3.selectbox("Repeat", ["once", "hourly", "daily", "weekly"])
        sc = {"schedule_time": datetime.combine(sd, stime).isoformat(), "recurrence": srec}
    b1, b2, b3 = st.columns(3)
    body = {"name": name or "Untitled", "description": desc or "", "workflow_type": wtype, "nodes": nodes}
    if b1.button("💾 Save workflow", type="primary", use_container_width=True, disabled=not nodes):
        try:
            w = api.put(f"/workflow/{ss['wf_id']}", body) if ss["wf_id"] else api.post("/workflow/create", body)
            ss["wf_id"] = w["id"]
            if sc:
                api.post("/tasks/schedule", {**sc, "workflow_id": w["id"]})
                st.success("Saved and scheduled")
            else:
                st.success("Saved")
        except ApiError as exc:
            st.error(str(exc))
    if b2.button("▶ Execute", use_container_width=True, disabled=not ss["wf_id"]):
        try:
            api.put(f"/workflow/{ss['wf_id']}", body)
            ss["wf_task"] = api.post(f"/workflow/{ss['wf_id']}/execute")["id"]
        except ApiError as exc:
            st.error(str(exc))
    if b3.button("🗑 Delete saved", use_container_width=True, disabled=not ss["wf_id"]):
        api.delete(f"/workflow/{ss['wf_id']}")
        ss.update(wf_id=None, wf_nodes=[])
        st.rerun()

if ss.get("wf_task"):
    st.subheader("Execution")
    tid = ss["wf_task"]
    try:
        t = api.get(f"/tasks/{tid}")
        draw(effective(nodes, wtype), {s["key"]: s["status"] for s in t["subtasks"]}, {s["key"]: s["result"] for s in t["subtasks"]})
        tm.show_active("wf_task")
    except ApiError as exc:
        st.error(str(exc))

if ss["wf_id"]:
    with st.expander("Workflow run history"):
        try:
            for t in api.get(f"/workflow/{ss['wf_id']}/history"):
                st.markdown(f"Task #{t['id']} {tm.pill(t['task_status'])} {t['created_at'][:19]} · {t.get('duration_seconds') or '-'}s", unsafe_allow_html=True)
        except ApiError as exc:
            st.error(str(exc))
