from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

from typing_extensions import NotRequired, TypedDict


class TaskStatus(str, Enum):
    DISCOVERY = "discovery"
    WAIT_HUMAN_REQUIREMENT = "wait_human_requirement"
    PLANNING = "planning"
    WAIT_HUMAN_PLAN = "wait_human_plan"
    CODING = "coding"
    TESTING = "testing"
    DEBUGGING = "debugging"
    WAIT_HUMAN_CODE = "wait_human_code"
    REVIEW = "review"
    WAIT_HUMAN_FINAL = "wait_human_final"
    PAUSED = "paused"
    DONE = "done"
    CANCELLED = "cancelled"
    FAILED = "failed"


class SessionMode(str, Enum):
    CHAT = "chat"
    PROJECT_ACTIVE = "project_active"


@dataclass(slots=True, frozen=True)
class ProjectRecord:
    id: str
    title: str
    requirement: str
    status: TaskStatus
    version: int
    current_checkpoint_id: str | None
    requires_human_takeover: bool
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class WechatSessionRecord:
    id: str
    wecom_user_id: str
    mode: SessionMode
    active_project_id: str | None
    conversation_summary: str
    last_requirement_draft: str | None
    pending_next_step: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True, frozen=True)
class CheckpointRecord:
    id: str
    project_id: str
    type: str
    status: str
    available_actions: list[str]
    created_at: datetime
    resolved_at: datetime | None


class RequirementSpec(TypedDict):
    summary: str
    open_questions: list[str]
    constraints: list[str]
    candidate_solutions: NotRequired[list[str]]
    assumptions: NotRequired[list[str]]
    risks: NotRequired[list[str]]
    recommended_direction: NotRequired[str | None]


class Plan(TypedDict):
    summary: str
    tasks: list[str]
    risks: list[str]
    milestones: NotRequired[list[str]]
    dependencies: NotRequired[list[str]]
    out_of_scope: NotRequired[list[str]]
    open_questions: NotRequired[list[str]]


class ReviewReport(TypedDict):
    approved: bool
    issues: list[str]
    risk_level: str
    summary: str


class HumanFeedback(TypedDict):
    target: str
    action: str
    comments: str
    rejection_reason_type: NotRequired[str | None]


class TestResult(TypedDict):
    status: str
    failure_type: str | None
    summary: str
    raw_logs: str


class DevelopmentState(TypedDict):
    requirement: str
    current_task: TaskStatus
    conversation: NotRequired[list[dict[str, str]] | None]
    requirement_spec: NotRequired[RequirementSpec | None]
    requirement_turn_mode: NotRequired[str | None]
    plan: NotRequired[Plan | None]
    human_feedback: NotRequired[HumanFeedback | None]
    code_files: NotRequired[dict[str, str] | None]
    test_results: NotRequired[TestResult | None]
    debug_summary: NotRequired[str | None]
    review_report: NotRequired[ReviewReport | None]


def utcnow() -> datetime:
    return datetime.now(tz=UTC)
