"""Page chrome: config, CSS, authentication gate and sidebar user panel."""
from __future__ import annotations

from pathlib import Path

import streamlit as st
from streamlit.errors import StreamlitAPIException

from components.api_client import ApiError, api

CSS = (Path(__file__).resolve().parent.parent / "assets" / "style.css").read_text(encoding="utf-8")


def _auth_screen() -> None:
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown('<div class="af-hero"><h1>AgentFlow AI</h1><p>Multi-agent task automation workspace</p></div>', unsafe_allow_html=True)
        login, reg = st.tabs(["Log in", "Create account"])
        with login:
            with st.form("login"):
                u, p = st.text_input("Username"), st.text_input("Password", type="password")
                if st.form_submit_button("Log in", type="primary", use_container_width=True):
                    _do_auth("/auth/login", {"username": u, "password": p})
        with reg:
            with st.form("register"):
                u, e = st.text_input("Username", key="ru"), st.text_input("Email")
                p = st.text_input("Password (8+ chars, letter + digit)", type="password", key="rp")
                if st.form_submit_button("Register", type="primary", use_container_width=True):
                    _do_auth("/auth/register", {"username": u, "email": e, "password": p})
            st.caption("The first account created becomes the administrator.")


def _do_auth(path: str, body: dict) -> None:
    try:
        data = api.post(path, body)
    except ApiError as exc:
        st.error(str(exc))
        return
    st.session_state["token"], st.session_state["user"] = data["access_token"], data["user"]
    st.rerun()


def setup_page() -> dict:
    try:
        st.set_page_config(page_title="AgentFlow AI", page_icon="🤖", layout="wide")
    except StreamlitAPIException:
        pass
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
    if "token" not in st.session_state:
        _auth_screen()
        st.stop()
    user = st.session_state["user"]
    with st.sidebar:
        st.markdown('<div class="af-brand">⚡ AgentFlow AI</div><div class="af-sub">Multi-agent automation</div>', unsafe_allow_html=True)
        st.caption(f"👤 **{user['username']}** · {user['role']}")
        if st.button("Log out", use_container_width=True):
            try:
                api.post("/auth/logout")
            except ApiError:
                pass
            st.session_state.clear()
            st.rerun()
    return user


def current_user() -> dict:
    return st.session_state["user"]


def header(title: str, subtitle: str = "") -> None:
    st.markdown(f'<div class="af-hero"><h1>{title}</h1><p>{subtitle}</p></div>', unsafe_allow_html=True)
