from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum

from llm import StructuredLLMClient
from workspace.state import WechatSessionRecord


class DirectorAction(str, Enum):
    CHAT_REPLY = "chat_reply"
    START_PROJECT = "start_project"
    PROJECT_QUERY = "project_query"


@dataclass(slots=True, frozen=True)
class DirectorDecision:
    action: DirectorAction
    message: str
    project_id: str | None = None
    requirement_draft: str | None = None
    conversation_summary: str | None = None


@dataclass(slots=True)
class DirectorAgent:
    model: str | None = None
    llm_client: StructuredLLMClient | None = None

    def run(self, message: str, session: WechatSessionRecord | None = None) -> DirectorDecision:
        if self.llm_client is None:
            return DirectorDecision(
                action=DirectorAction.CHAT_REPLY,
                message="我先继续和你澄清需求，不会自动进入开发流程。",
            )

        payload = self.llm_client.generate_json(
            instructions=(
                "You are the director agent for a software development assistant. "
                "Return a JSON object with keys: action, reply, requirement_draft, conversation_summary, project_id. "
                "Allowed action values are chat_reply, start_project, project_query. "
                "Only choose start_project when the user explicitly asks to start development."
            ),
            input_text=json.dumps(
                {
                    "message": message,
                    "session": {
                        "mode": session.mode.value if session is not None else None,
                        "active_project_id": session.active_project_id if session is not None else None,
                        "conversation_summary": session.conversation_summary if session is not None else None,
                        "last_requirement_draft": session.last_requirement_draft if session is not None else None,
                    },
                },
                ensure_ascii=False,
            ),
        )
        return DirectorDecision(
            action=_coerce_action(payload.get("action")),
            message=str(payload.get("reply") or "我先继续和你澄清需求，不会自动进入开发流程。"),
            project_id=_optional_text(payload.get("project_id")),
            requirement_draft=_optional_text(payload.get("requirement_draft")),
            conversation_summary=_optional_text(payload.get("conversation_summary")),
        )


def _coerce_action(value: object) -> DirectorAction:
    if isinstance(value, str):
        normalized = value.strip().lower()
        for action in DirectorAction:
            if action.value == normalized:
                return action
    return DirectorAction.CHAT_REPLY


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
