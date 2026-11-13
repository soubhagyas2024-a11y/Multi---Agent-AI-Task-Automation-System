import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import streamlit as st  # noqa: E402

from components.api_client import ApiError, api  # noqa: E402
from components.sidebar import header  # noqa: E402

header("AI Memory", "Preferences, facts and task summaries the agents recall automatically. Private to you.")
with st.form("addmem", clear_on_submit=True):
    c1, c2 = st.columns([4, 1])
    content = c1.text_input("Remember this", placeholder="e.g. I prefer concise answers with bullet points")
    cat = c2.selectbox("Category", ["preference", "fact", "note"])
    if st.form_submit_button("Save memory", type="primary") and content.strip():
        try:
            api.post("/memory", {"content": content, "category": cat})
            st.rerun()
        except ApiError as exc:
            st.error(str(exc))
q = st.text_input("🔍 Search memories")
try:
    mems = api.get("/memory" + (f"?q={q}" if q else ""))
except ApiError as exc:
    st.error(str(exc))
    st.stop()
if not mems:
    st.info("No memories yet. Completed tasks are summarised here automatically.")
for m in mems:
    c1, c2 = st.columns([8, 1])
    c1.markdown(f"`{m['memory_category']}` {m['memory_content']}  \n<span style='color:#8a96b2;font-size:.75rem'>{m['created_at'][:19]}</span>", unsafe_allow_html=True)
    if c2.button("🗑", key=f"dm{m['id']}"):
        api.delete(f"/memory/{m['id']}")
        st.rerun()
