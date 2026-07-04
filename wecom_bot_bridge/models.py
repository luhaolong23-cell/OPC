from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TextMessageEvent(BaseModel):
    message_id: str = Field(min_length=1)
    wecom_user_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    is_group_chat: bool = False
    raw_frame: dict[str, Any] = Field(default_factory=dict)


class OpcWechatEventResponse(BaseModel):
    action: str
    reply: str
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
