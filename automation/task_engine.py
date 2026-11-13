"""Reusable task execution engine.

Pipeline: instruction -> intent recognition -> planning -> agent assignment -> permission check ->
execution -> verification -> output. Runs tasks asynchronously in a thread pool, supports cancel,
pause/resume (re-submit), approval resumption, timeouts and crash recovery.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor

from backend.config import settings
from backend.database import session_scope
from backend.models import Task, User
from backend.services import task_service as ts
from utils.helpers import control, log_event, utcnow
from utils.logger import get_logger
from workflows.graph import get_graph

logger = get_logger("engine")


class EngineBusy(RuntimeError):
    pass


class TaskEngine:
    def __init__(self) -> None:
        self._pool = ThreadPoolExecutor(max_workers=settings.max_concurrent_tasks, thread_name_prefix="agentflow-task")
        self._futures: dict[int, Future] = {}
        self._lock = threading.Lock()

    def is_running(self, task_id: int) -> bool:
        f = self._futures.get(task_id)
        return bool(f and not f.done())

    def active_ids(self) -> list[int]:
        return [i for i, f in self._futures.items() if not f.done()]

    def _permission_check(self, task_id: int) -> None:
        with session_scope() as db:
            t = db.get(Task, task_id)
            u = db.get(User, t.user_id) if t else None
            if not t or not u or not u.is_active:
                raise PermissionError("Task owner is missing or disabled")

    def submit(self, task_id: int) -> None:
        with self._lock:
            if self.is_running(task_id):
                raise EngineBusy("Task is already running")
            self._permission_check(task_id)
            control.reset(task_id)
            with session_scope() as db:
                t = db.get(Task, task_id)
                t.task_status = "running"
                t.started_at = t.started_at or utcnow()
                t.completed_at = None
            self._futures[task_id] = self._pool.submit(self._run, task_id)

    def _run(self, task_id: int) -> None:
        try:
            state = ts.build_initial_state(task_id)
            state["started_at"] = time.time()
            get_graph().invoke(state, config={"recursion_limit": 60})
        except Exception as exc:  # noqa: BLE001
            logger.exception("Task %s crashed", task_id)
            log_event(task_id, "coordinator", "crash", f"{type(exc).__name__}: {exc}", "ERROR")
            ts.finish_task(task_id, "failed", "", f"Internal error: {type(exc).__name__}")
        finally:
            control.reset(task_id)

    def cancel(self, task_id: int) -> None:
        if self.is_running(task_id):
            control.request_cancel(task_id)
        else:
            ts.finish_task(task_id, "cancelled", "Cancelled before completion")

    def pause(self, task_id: int) -> None:
        if not self.is_running(task_id):
            raise EngineBusy("Task is not running")
        control.request_pause(task_id)


engine = TaskEngine()
