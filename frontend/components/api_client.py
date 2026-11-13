"""Thin HTTP client for the FastAPI backend (token kept in Streamlit session state)."""
from __future__ import annotations

import os

import requests
import streamlit as st

BASE = os.getenv("AGENTFLOW_API_URL", "http://127.0.0.1:8000")


class ApiError(Exception):
    pass


class Api:
    def _request(self, method: str, path: str, **kw):
        token = st.session_state.get("token")
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            r = requests.request(method, BASE + path, headers=headers, timeout=kw.pop("timeout", 30), **kw)
        except requests.ConnectionError:
            raise ApiError(f"Cannot reach the backend at {BASE}. Start it with run_backend.bat (python -m uvicorn backend.main:app).")
        except requests.Timeout:
            raise ApiError("The backend took too long to respond.")
        if r.status_code == 401 and token:
            for k in ("token", "user"):
                st.session_state.pop(k, None)
            raise ApiError("Session expired - please log in again.")
        if r.status_code >= 400:
            try:
                d = r.json().get("detail", r.text)
            except ValueError:
                d = r.text
            raise ApiError(d if isinstance(d, str) else "; ".join(str(x.get("msg", x)) for x in d))
        return r

    def get(self, path, **kw):
        return self._request("GET", path, **kw).json()

    def post(self, path, json=None, **kw):
        return self._request("POST", path, json=json, **kw).json()

    def put(self, path, json=None):
        return self._request("PUT", path, json=json).json()

    def delete(self, path):
        return self._request("DELETE", path).json()

    def upload(self, name: str, data: bytes) -> dict:
        return self._request("POST", "/files/upload", files={"file": (name, data)}, timeout=60).json()

    def download(self, file_id: int) -> bytes:
        return self._request("GET", f"/files/{file_id}/download", timeout=60).content


api = Api()
