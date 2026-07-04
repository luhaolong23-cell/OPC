from __future__ import annotations

from director.agent import DirectorAction, DirectorAgent, DirectorDecision
from workspace.state import SessionMode, WechatSessionRecord


class UnsupportedConversationError(RuntimeError):
    """Raised when the conversation type is outside the MVP scope."""


class ActiveProjectError(RuntimeError):
    """Raised when a user tries to start another active project."""


ACTIVE_PROJECT_ERROR_MESSAGE = "你已有进行中的项目，请先发送 状态 或 批准。"


class DirectorRouter:
    def __init__(self, agent: DirectorAgent | None = None) -> None:
        self.agent = agent

    def route_message(
        self,
        message: str,
        session: WechatSessionRecord | None = None,
        *,
        is_group_chat: bool = False,
    ) -> DirectorDecision:
        normalized = message.strip()

        if is_group_chat:
            raise UnsupportedConversationError("group chat is not supported in MVP")

        if (
            session is not None
            and session.mode is SessionMode.PROJECT_ACTIVE
            and session.active_project_id is not None
            and self._is_project_query(normalized)
        ):
            return DirectorDecision(
                action=DirectorAction.PROJECT_QUERY,
                message="我来查询当前项目进度。",
                project_id=session.active_project_id,
            )

        if self.agent is not None and self._should_use_agent():
            decision = self.agent.run(normalized, session=session)
            if decision.action is DirectorAction.START_PROJECT:
                if not self._is_start_project_message(normalized):
                    return DirectorDecision(
                        action=DirectorAction.CHAT_REPLY,
                        message=decision.message,
                        requirement_draft=decision.requirement_draft,
                        conversation_summary=decision.conversation_summary,
                    )
                if (
                    session is not None
                    and session.mode is SessionMode.PROJECT_ACTIVE
                    and session.active_project_id is not None
                ):
                    raise ActiveProjectError(ACTIVE_PROJECT_ERROR_MESSAGE)
            if decision.action is DirectorAction.PROJECT_QUERY and decision.project_id is None and session is not None:
                return DirectorDecision(
                    action=decision.action,
                    message=decision.message,
                    project_id=session.active_project_id,
                    requirement_draft=decision.requirement_draft,
                    conversation_summary=decision.conversation_summary,
                )
            return decision

        if self._is_start_project_message(normalized):
            if (
                session is not None
                and session.mode is SessionMode.PROJECT_ACTIVE
                and session.active_project_id is not None
            ):
                raise ActiveProjectError(ACTIVE_PROJECT_ERROR_MESSAGE)
            return DirectorDecision(
                action=DirectorAction.START_PROJECT,
                message="已收到开始开发请求，我会创建项目并进入开发流程。",
            )

        return DirectorDecision(
            action=DirectorAction.CHAT_REPLY,
            message="我先继续和你澄清需求，不会自动进入开发流程。",
        )

    def _should_use_agent(self) -> bool:
        if self.agent is None:
            return False
        if not hasattr(self.agent, "llm_client"):
            return True
        return getattr(self.agent, "llm_client") is not None

    @staticmethod
    def _is_start_project_message(message: str) -> bool:
        return "开始开发" in message

    @staticmethod
    def _is_project_query(message: str) -> bool:
        keywords = ("进度", "状态", "阶段", "卡在哪")
        return any(keyword in message for keyword in keywords)
