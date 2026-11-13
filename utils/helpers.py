"""Shared helpers: time, safe paths, JSON extraction, task control flags, DB log events."""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.logger import get_logger

logger = get_logger("helpers")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def truncate(text: Any, n: int = 2000) -> str:
    s = "" if text is None else str(text)
    return s if len(s) <= n else s[:n] + " …[truncated]"


def safe_join(base: Path, *parts: str) -> Path:
    """Join `parts` onto `base`; raise PermissionError if the result escapes `base`."""
    base = Path(base).resolve()
    target = base.joinpath(*parts).resolve()
    if target != base and base not in target.parents:
        raise PermissionError("Path escapes the allowed workspace")
    return target


def extract_json(text: str) -> Any:
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.I)
    try:
        return json.loads(t)
    except ValueError:
        pass
    dec = json.JSONDecoder()
    for i, ch in enumerate(t):
        if ch in "{[":
            try:
                return dec.raw_decode(t[i:])[0]
            except ValueError:
                continue
    raise ValueError("No JSON found in model output")


_CATS = {
    "research": ("research", "search", "latest", "find out", "sources", "news", "investigate"),
    "data": ("csv", "excel", "xlsx", "dataset", "chart", "statistic", "analy"),
    "coding": ("code", "python", "script", "function", "debug", "bug", "program", "class "),
    "document": ("report", "document", "pdf", "docx", "word file", "email", "summary", "summar", "minutes", "memo", "write"),
    "file": ("folder", "rename", "organi", "text file", "create file", "delete file", "directory"),
}


def detect_category(text: str) -> str:
    """Intent recognition (keyword based, no LLM call)."""
    t = (text or "").lower()
    scores = {c: sum(k in t for k in kws) for c, kws in _CATS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else "general"


class TaskControl:
    """Thread-safe cancel / pause flags shared between the engine, API and graph nodes."""

    def __init__(self) -> None:
        self._cancel: set[int] = set()
        self._pause: set[int] = set()
        self._lock = threading.Lock()

    def request_cancel(self, tid: int) -> None:
        with self._lock:
            self._cancel.add(tid)

    def request_pause(self, tid: int) -> None:
        with self._lock:
            self._pause.add(tid)

    def is_cancelled(self, tid: int) -> bool:
        return tid in self._cancel

    def is_paused(self, tid: int) -> bool:
        return tid in self._pause

    def reset(self, tid: int) -> None:
        with self._lock:
            self._cancel.discard(tid)
            self._pause.discard(tid)


control = TaskControl()


def log_event(task_id: int | None, agent: str, action: str, output: Any = "", level: str = "INFO") -> None:
    """Persist an execution log row; never raises."""
    try:
        from backend.database import session_scope
        from backend.models import ExecutionLog

        with session_scope() as db:
            db.add(ExecutionLog(task_id=task_id, agent_name=agent, action=action, output=truncate(output, 4000), level=level))
    except Exception:  # noqa: BLE001
        logger.exception("Failed to write execution log")
