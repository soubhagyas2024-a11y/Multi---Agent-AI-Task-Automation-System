import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import streamlit as st  # noqa: E402

from components import agent_cards  # noqa: E402
from components.api_client import ApiError, api  # noqa: E402
from components.sidebar import current_user, header  # noqa: E402

header("Agent Management", "Specialised agents, their responsibilities and live performance.")
try:
    agents = api.get("/agents")
    live = api.get("/analytics/live")
except ApiError as exc:
    st.error(str(exc))
    st.stop()
if current_user()["role"] != "admin":
    st.caption("Only administrators can enable or disable agents.")
agent_cards.render(agents, current_user()["role"] == "admin")
st.subheader("Currently executing")
if live["running"]:
    for t in live["running"]:
        st.markdown(f"**#{t['id']}** {t['description']} — `{t['status']}`")
else:
    st.caption("No tasks are running.")
