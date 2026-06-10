from __future__ import annotations

import enum
import json
from datetime import datetime

from pydantic import BaseModel, Field


class Outcome(enum.StrEnum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILURE = "FAILURE"
    ABORTED = "ABORTED"


class HeuristicStatus(enum.StrEnum):
    CANDIDATE = "CANDIDATE"
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    REVERTED = "REVERTED"


class OriginType(enum.StrEnum):
    EXTRACTED = "EXTRACTED"
    TAUGHT = "TAUGHT"
    IMPORTED = "IMPORTED"


class EvidenceDirection(enum.StrEnum):
    SUPPORTING = "SUPPORTING"
    CONTRADICTING = "CONTRADICTING"


class FailureModelStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"
    DEPRECATED = "DEPRECATED"


class ChangeOperation(enum.StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    STATUS_CHANGE = "STATUS_CHANGE"
    EVIDENCE_ADD = "EVIDENCE_ADD"
    REVERT = "REVERT"
    DELETE = "DELETE"


class Scope(BaseModel):
    domains: list[str] = Field(default_factory=lambda: ["*"])
    tools: list[str] = Field(default_factory=lambda: ["*"])
    tags: list[str] = Field(default_factory=lambda: ["*"])
    projects: list[str] = Field(default_factory=lambda: ["*"])
    conditions: str = ""

    @property
    def summary(self) -> str:
        parts = []
        if self.domains != ["*"]:
            parts.append(f"domains={self.domains}")
        if self.tags != ["*"]:
            parts.append(f"tags={self.tags}")
        if self.conditions:
            parts.append(self.conditions)
        return ", ".join(parts) if parts else "all tasks"


class CostBreakdown(BaseModel):
    total_inr: float = 0.0
    by_tier: dict[str, float] = Field(default_factory=dict)
    tokens_total: int = 0
    duration_s: float = 0.0


class Episode(BaseModel):
    id: str
    goal: str
    context_features: dict = Field(default_factory=dict)
    action_trace: list[dict] = Field(default_factory=list)
    outcome: Outcome
    outcome_detail: str | None = None
    lessons_applied: list[str] = Field(default_factory=list)
    failure_models_checked: list[str] = Field(default_factory=list)
    cost_breakdown: CostBreakdown = Field(default_factory=CostBreakdown)
    started_at: datetime
    completed_at: datetime
    created_at: datetime | None = None


class Heuristic(BaseModel):
    id: str
    statement: str
    scope: Scope = Field(default_factory=Scope)
    status: HeuristicStatus = HeuristicStatus.CANDIDATE
    supporting: float = 0
    contradicting: float = 0
    confidence: float = 0.5
    origin_type: OriginType = OriginType.EXTRACTED
    origin_episode_id: str | None = None
    promoted_at: datetime | None = None
    deprecated_at: datetime | None = None
    last_applied_at: datetime | None = None
    last_evidence_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Evidence(BaseModel):
    id: str
    heuristic_id: str
    episode_id: str
    direction: EvidenceDirection
    weight: float = 1.0
    reasoning: str | None = None
    is_origin: bool = False
    created_at: datetime | None = None


class FailureModel(BaseModel):
    id: str
    signature: str
    root_cause: str
    recovery_path: list[str] = Field(default_factory=list)
    scope: Scope = Field(default_factory=Scope)
    trigger_count: int = 1
    last_triggered_at: datetime | None = None
    source_episodes: list[str] = Field(default_factory=list)
    status: FailureModelStatus = FailureModelStatus.ACTIVE
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ChangelogEntry(BaseModel):
    seq: int | None = None
    hash: str = ""
    prev_hash: str = ""
    timestamp: datetime | None = None
    entity_type: str
    entity_id: str
    operation: ChangeOperation
    field_changes: dict = Field(default_factory=dict)
    reason: str | None = None
    snapshot: dict = Field(default_factory=dict)


def row_to_episode(row: dict | object) -> Episode:
    r = dict(row) if not isinstance(row, dict) else row
    return Episode(
        id=r["id"],
        goal=r["goal"],
        context_features=json.loads(r["context_features"]),
        action_trace=json.loads(r["action_trace"]),
        outcome=r["outcome"],
        outcome_detail=r.get("outcome_detail"),
        lessons_applied=json.loads(r["lessons_applied"]),
        failure_models_checked=json.loads(r.get("failure_models_checked", "[]")),
        cost_breakdown=CostBreakdown(**json.loads(r["cost_breakdown"])),
        started_at=r["started_at"],
        completed_at=r["completed_at"],
        created_at=r.get("created_at"),
    )


def row_to_heuristic(row: dict | object) -> Heuristic:
    r = dict(row) if not isinstance(row, dict) else row
    return Heuristic(
        id=r["id"],
        statement=r["statement"],
        scope=Scope(**json.loads(r["scope"])),
        status=r["status"],
        supporting=r["supporting"],
        contradicting=r["contradicting"],
        confidence=r["confidence"],
        origin_type=r["origin_type"],
        origin_episode_id=r.get("origin_episode_id"),
        promoted_at=r.get("promoted_at"),
        deprecated_at=r.get("deprecated_at"),
        last_applied_at=r.get("last_applied_at"),
        last_evidence_at=r.get("last_evidence_at"),
        created_at=r.get("created_at"),
        updated_at=r.get("updated_at"),
    )


def row_to_evidence(row: dict | object) -> Evidence:
    r = dict(row) if not isinstance(row, dict) else row
    return Evidence(
        id=r["id"],
        heuristic_id=r["heuristic_id"],
        episode_id=r["episode_id"],
        direction=r["direction"],
        weight=r["weight"],
        reasoning=r.get("reasoning"),
        is_origin=bool(r["is_origin"]),
        created_at=r.get("created_at"),
    )


def row_to_changelog(row: dict | object) -> ChangelogEntry:
    r = dict(row) if not isinstance(row, dict) else row
    return ChangelogEntry(
        seq=r.get("seq"),
        hash=r["hash"],
        prev_hash=r["prev_hash"],
        timestamp=r.get("timestamp"),
        entity_type=r["entity_type"],
        entity_id=r["entity_id"],
        operation=r["operation"],
        field_changes=json.loads(r["field_changes"]),
        reason=r.get("reason"),
        snapshot=json.loads(r["snapshot"]),
    )
