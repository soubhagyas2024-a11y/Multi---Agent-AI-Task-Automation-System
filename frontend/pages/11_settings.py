import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import streamlit as st  # noqa: E402

from components.api_client import BASE, ApiError, api  # noqa: E402
from components.sidebar import current_user, header  # noqa: E402

header("Settings", "Connection status and configuration.")
u = current_user()
st.subheader("Account")
st.write(f"**{u['username']}** · {u['email']} · role: `{u['role']}`")
st.subheader("Backend")
try:
    h = api.get("/health")
    st.success(f"Connected to {BASE}")
    st.write(f"Gemini API key: {'✅ configured' if h['gemini_configured'] else '❌ missing (set GEMINI_API_KEY in .env and restart the backend)'}")
    st.write(f"Tavily API key: {'✅ configured' if h['tavily_configured'] else '❌ missing (set TAVILY_API_KEY in .env - needed by the Research Agent)'}")
except ApiError as exc:
    st.error(str(exc))
if u["role"] == "admin":
    st.subheader("System configuration (read-only)")
    try:
        st.json(api.get("/admin/system"))
    except ApiError as exc:
        st.error(str(exc))
    st.caption("API keys live only in the backend .env file and are never sent to the browser.")
