from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    channel: str = "api"


class CreateSessionResponse(BaseModel):
    session_id: str
    channel: str
    started_at: datetime


class SubmitTaskRequest(BaseModel):
    session_id: str | None = None
    goal: str
    domain: str = ""
    tags: list[str] = Field(default_factory=list)


class TaskResponse(BaseModel):
    outcome: str
    summary: str
    episode_id: str | None = None
    cost_inr: float = 0.0


class TeachRequest(BaseModel):
    statement: str
    domain: str = ""
    tags: list[str] = Field(default_factory=list)


class TeachResponse(BaseModel):
    heuristic_id: str
    statement: str
    confidence: float
    status: str


class LessonResponse(BaseModel):
    id: str
    statement: str
    status: str
    confidence: float
    supporting: float
    contradicting: float
    scope_summary: str
    created_at: datetime | None = None


class GrantPermissionRequest(BaseModel):
    capability: str
    scope: str = "*"


class PermissionResponse(BaseModel):
    id: str
    capability: str
    scope: str


class KillRequest(BaseModel):
    reason: str = "API kill"


class KillResponse(BaseModel):
    triggered_at: str
    reason: str
    killed_sessions: int
    revoked_permissions: int


class BudgetResponse(BaseModel):
    date: str
    spent_inr: float
    limit_inr: float
    count: int


class StatusResponse(BaseModel):
    active_sessions: int
    budget: BudgetResponse
    kill_switch: bool


class SessionStatusResponse(BaseModel):
    id: str
    channel: str
    status: str
    started_at: datetime
    task_count: int
    total_cost_inr: float
    current_task: str | None = None


class WSMessageType(enum.StrEnum):
    CHAT_MESSAGE = "chat.message"
    CHAT_CANCEL = "chat.cancel"
    PERMISSION_GRANT = "permission.grant"
    PERMISSION_REVOKE = "permission.revoke"
    BRAIN_TEACH = "brain.teach"
    KILL = "kill"


class WSMessage(BaseModel):
    type: WSMessageType
    data: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: str
    detail: str = ""
