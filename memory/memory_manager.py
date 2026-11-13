"""Persistent per-user memory (SQLite) + short-term per-task memory. All queries are user-scoped."""
from __future__ import annotations

import threading
from typing import Optional

from backend.database import session_scope
from backend.models import Memory
from memory.retrieval import rank


class MemoryManager:
    @staticmethod
    def add(user_id: int, content: str, category: str = "note") -> int:
        content = content.strip()[:2000]
        with session_scope() as db:
            dup = db.query(Memory).filter_by(user_id=user_id, memory_content=content).first()
            if dup:
                return dup.id
            m = Memory(user_id=user_id, memory_content=content, memory_category=category)
            db.add(m)
            db.flush()
            return m.id

    @staticmethod
    def list(user_id: int, category: Optional[str] = None, q: Optional[str] = None, limit: int = 200) -> list[Memory]:
        with session_scope() as db:
            query = db.query(Memory).filter_by(user_id=user_id)
            if category:
                query = query.filter_by(memory_category=category)
            items = query.order_by(Memory.id.desc()).limit(limit).all()
        return rank(items, q, k=limit) if q else items

    @staticmethod
    def update(user_id: int, memory_id: int, content: str) -> bool:
        with session_scope() as db:
            m = db.query(Memory).filter_by(id=memory_id, user_id=user_id).first()
            if not m:
                return False
            m.memory_content = content.strip()[:2000]
            return True

    @staticmethod
    def delete(user_id: int, memory_id: int) -> bool:
        with session_scope() as db:
            return db.query(Memory).filter_by(id=memory_id, user_id=user_id).delete() > 0

    @staticmethod
    def search(user_id: int, query: str, k: int = 5) -> list[Memory]:
        return rank(MemoryManager.list(user_id, limit=500), query, k=k)


class ShortTermMemory:
    """Scratchpad that lives only for the duration of a task."""

    def __init__(self) -> None:
        self._data: dict[int, dict] = {}
        self._lock = threading.Lock()

    def put(self, task_id: int, key: str, value) -> None:
        with self._lock:
            self._data.setdefault(task_id, {})[key] = value

    def get(self, task_id: int, key: str, default=None):
        return self._data.get(task_id, {}).get(key, default)

    def clear(self, task_id: int) -> None:
        with self._lock:
            self._data.pop(task_id, None)


short_term = ShortTermMemory()
