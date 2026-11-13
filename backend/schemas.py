"""Pydantic request schemas (responses are plain JSON dicts built by the services)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class RegisterIn(BaseModel):
    username: str
    email: str
    password: str


class LoginIn(BaseModel):
    username: str
    password: str


class TaskCreate(BaseModel):
    description: str = Field(min_length=3, max_length=5000)
    priority: Literal["low", "normal", "high"] = "normal"
    file_ids: list[int] = Field(default_factory=list, max_length=10)
    agents: list[str] = Field(default_factory=list, description="Optionally restrict planning to these agents")
    execute: bool = True


class ApprovalIn(BaseModel):
    approved: bool


class MemoryIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
    category: Literal["preference", "fact", "summary", "note"] = "note"


class WorkflowNode(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    agent: str
    instruction: str = Field(default="", max_length=2000)
    depends_on: list[str] = Field(default_factory=list)
    condition: Optional[dict] = Field(default=None, description='{"source": node_id, "contains": text, "negate": bool}')


class WorkflowIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    workflow_type: Literal["sequential", "parallel", "conditional", "scheduled"] = "sequential"
    nodes: list[WorkflowNode] = Field(min_length=1, max_length=12)


class ScheduleIn(BaseModel):
    description: str = Field(default="", max_length=5000)
    schedule_time: datetime
    recurrence: Literal["once", "hourly", "daily", "weekly"] = "once"
    workflow_id: Optional[int] = None

    @model_validator(mode="after")
    def _need_target(self):
        if not self.workflow_id and len(self.description.strip()) < 3:
            raise ValueError("Provide a task description or a workflow_id")
        return self
