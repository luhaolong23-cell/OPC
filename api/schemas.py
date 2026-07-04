from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ProjectResponse(BaseModel):
    id: str
    title: str
    requirement: str
    status: str
    version: int
    current_checkpoint_id: str | None
    requires_human_takeover: bool
    created_at: datetime
    updated_at: datetime


class CheckpointResponse(BaseModel):
    id: str
    project_id: str
    type: str
    status: str
    available_actions: list[str]
    created_at: datetime
    resolved_at: datetime | None


class CreateProjectRequest(BaseModel):
    title: str | None = None
    requirement: str = Field(min_length=1)


class CreateProjectEnvelope(BaseModel):
    project: ProjectResponse


class ProjectRunResponse(BaseModel):
    project: ProjectResponse
    checkpoint: CheckpointResponse | None = None


class FeedbackRequest(BaseModel):
    checkpoint_id: str
    checkpoint_type: str
    action: str
    comments: str = ''
    rejection_reason_type: str | None = None
    client_version: int


class FeedbackResponse(BaseModel):
    accepted: bool
    project: ProjectResponse
    checkpoint: CheckpointResponse | None = None


class WechatCardCallbackRequest(BaseModel):
    project_id: str
    checkpoint_id: str
    checkpoint_type: str
    action: str
    comments: str = ''
    rejection_reason_type: str | None = None
    client_version: int


class WechatEventRequest(BaseModel):
    wecom_user_id: str
    message: str = Field(min_length=1)
    is_group_chat: bool = False


class WechatEventResponse(BaseModel):
    action: str
    reply: str
    project: ProjectResponse | None = None
    project_id: str | None = None


class InternalNotifyRequest(BaseModel):
    event_id: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    wecom_user_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    status: str = Field(min_length=1)
    checkpoint_type: str | None = None


class InternalNotifyResponse(BaseModel):
    accepted: bool
