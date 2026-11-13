"""ORM models."""
from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text

from backend.database import Base
from utils.helpers import utcnow


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(128), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    role = Column(String(16), default="user", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow)


class Agent(Base):
    __tablename__ = "agents"
    id = Column(Integer, primary_key=True)
    agent_name = Column(String(64), unique=True, nullable=False)
    description = Column(Text, default="")
    status = Column(String(16), default="idle")  # idle | busy | disabled
    tasks_completed = Column(Integer, default=0)
    tasks_failed = Column(Integer, default=0)
    success_rate = Column(Float, default=100.0)
    total_seconds = Column(Float, default=0.0)
    last_active = Column(DateTime, nullable=True)


class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    task_description = Column(Text, nullable=False)
    task_status = Column(String(24), default="pending", index=True)
    priority = Column(String(8), default="normal")
    category = Column(String(16), default="general")
    created_at = Column(DateTime, default=utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    plan_json = Column(Text, default="{}")  # objective, mode, file_ids, preferred agents
    workflow_id = Column(Integer, nullable=True)
    scheduled_id = Column(Integer, nullable=True)


class Subtask(Base):
    __tablename__ = "subtasks"
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    key = Column(String(32), nullable=False)
    assigned_agent = Column(String(64), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(24), default="pending")
    result = Column(Text, nullable=True)
    depends_on = Column(Text, default="[]")
    meta = Column(Text, default="{}")
    attempts = Column(Integer, default=0)


class ExecutionLog(Base):
    __tablename__ = "execution_logs"
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True, index=True)
    agent_name = Column(String(64))
    action = Column(String(64))
    output = Column(Text)
    level = Column(String(8), default="INFO")
    timestamp = Column(DateTime, default=utcnow, index=True)


class Memory(Base):
    __tablename__ = "memories"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    memory_content = Column(Text, nullable=False)
    memory_category = Column(String(24), default="note")
    created_at = Column(DateTime, default=utcnow)


class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    task_description = Column(Text, default="")
    schedule_time = Column(DateTime, nullable=False)
    recurrence = Column(String(16), default="once")
    status = Column(String(16), default="active")  # active | completed | cancelled
    workflow_id = Column(Integer, nullable=True)
    last_run = Column(DateTime, nullable=True)


class GeneratedFile(Base):
    __tablename__ = "generated_files"
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(200), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_type = Column(String(16))
    kind = Column(String(12), default="generated")  # generated | upload
    created_at = Column(DateTime, default=utcnow)


class Workflow(Base):
    __tablename__ = "workflows"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, default="")
    workflow_type = Column(String(16), default="sequential")
    definition = Column(Text, default="{}")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
