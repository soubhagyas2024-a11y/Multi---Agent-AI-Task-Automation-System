from __future__ import annotations

import streamlit as st

from components.api_client import ApiError, api

ICONS = {"coordinator": "🧭", "planner": "🗺️", "researcher": "🔎", "data_analyst": "📊", "coder": "💻", "writer": "✍️", "executor": "⚙️", "verifier": "✅", "memory": "🧠"}


def render(agents: list[dict], can_manage: bool) -> None:
    for row in range(0, len(agents), 3):
        cols = st.columns(3)
        for col, a in zip(cols, agents[row:row + 3]):
            with col:
                st.markdown(
                    f'<div class="af-card"><div style="font-size:1.5rem">{ICONS.get(a["agent_name"], "🤖")} <b>{a["title"]}</b> '
                    f'<span class="pill {a["status"]}" style="float:right">{a["status"]}</span></div>'
                    f'<p style="color:#8a96b2;font-size:.85rem;min-height:56px">{a["description"]}</p>'
                    f'<div style="font-size:.8rem">✔ {a["tasks_completed"]} completed · ✖ {a["tasks_failed"]} failed · '
                    f'<b>{a["success_rate"]:.0f}%</b> success<br><span style="color:#8a96b2">Last active: {(a["last_active"] or "never")[:19].replace("T", " ")}</span></div></div>',
                    unsafe_allow_html=True)
                if a["core"]:
                    st.caption("Core agent - always on")
                else:
                    on = st.toggle("Enabled", value=a["enabled"], key=f"tg_{a['id']}", disabled=not can_manage)
                    if can_manage and on != a["enabled"]:
                        try:
                            api.post(f"/agents/{a['id']}/{'enable' if on else 'disable'}")
                            st.rerun()
                        except ApiError as exc:
                            st.error(str(exc))
