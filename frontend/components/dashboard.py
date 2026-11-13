"""Metric cards and Plotly charts shared by Overview and Analytics (all data from the API)."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

PALETTE = ["#4f8cff", "#8b5cf6", "#34d399", "#fbbf24", "#f87171", "#22d3ee", "#f472b6"]


def metric_card(label: str, value, sub: str = "") -> None:
    st.markdown(f'<div class="af-card af-metric"><div class="l">{label}</div><div class="v">{value}</div><div class="s">{sub}</div></div>', unsafe_allow_html=True)


def _style(fig: go.Figure, h: int = 300) -> go.Figure:
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=h,
                      margin=dict(l=10, r=10, t=40, b=10), colorway=PALETTE, font=dict(family="Inter, Segoe UI, sans-serif"))
    return fig


def empty(msg: str = "No data yet - run a task to see this chart.") -> None:
    st.info(msg)


def daily_chart(daily: list[dict]):
    if not daily:
        return empty()
    df = pd.DataFrame(daily)
    fig = go.Figure()
    fig.add_bar(x=df["date"], y=df["completed"], name="Completed", marker_color="#34d399")
    fig.add_bar(x=df["date"], y=df["failed"], name="Failed", marker_color="#f87171")
    fig.add_scatter(x=df["date"], y=df["total"], name="Created", mode="lines+markers", line=dict(color="#4f8cff"))
    fig.update_layout(barmode="stack", title="Daily task activity")
    st.plotly_chart(_style(fig), use_container_width=True)


def agent_chart(agents: list[dict]):
    df = pd.DataFrame([a for a in agents if a["subtasks"]])
    if df.empty:
        return empty()
    fig = px.bar(df, x="title", y=["completed", "failed"], barmode="group", title="Agent performance", labels={"value": "Subtasks", "title": ""},
                 color_discrete_map={"completed": "#4f8cff", "failed": "#f87171"})
    st.plotly_chart(_style(fig), use_container_width=True)


def status_chart(status: dict):
    if not status:
        return empty()
    fig = px.pie(names=list(status), values=list(status.values()), hole=.55, title="Task status")
    st.plotly_chart(_style(fig), use_container_width=True)


def utilisation_chart(agents: list[dict]):
    df = pd.DataFrame([a for a in agents if a["subtasks"]])
    if df.empty:
        return empty()
    fig = px.pie(df, names="title", values="utilisation", hole=.55, title="Agent utilisation (%)")
    st.plotly_chart(_style(fig), use_container_width=True)


def category_chart(cats: dict):
    if not cats:
        return empty()
    fig = px.bar(x=list(cats), y=list(cats.values()), title="Task categories", labels={"x": "", "y": "Tasks"})
    st.plotly_chart(_style(fig), use_container_width=True)


def duration_chart(durations: list[dict]):
    if not durations:
        return empty()
    df = pd.DataFrame(durations)
    fig = px.scatter(df, x="id", y="seconds", color="category", title="Execution time per task (s)", labels={"id": "Task ID"})
    st.plotly_chart(_style(fig), use_container_width=True)


def timeline(events: list[dict], n: int = 12) -> None:
    if not events:
        return empty("No activity yet.")
    rows = "".join(f'<div class="e"><b>{e["agent"]}</b> · {e["action"]} <span style="opacity:.6">— task #{e["task_id"]} · {e["timestamp"][11:19]}</span></div>' for e in events[:n])
    st.markdown(f'<div class="af-tl">{rows}</div>', unsafe_allow_html=True)
