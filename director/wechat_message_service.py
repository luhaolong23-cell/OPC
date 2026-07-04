from __future__ import annotations

from dataclasses import dataclass

from api.schemas import ProjectResponse, WechatEventResponse
from director.agent import DirectorAction
from director.router import DirectorRouter
from graph.runtime import WorkflowService
from workspace.manager import WorkspaceManager
from workspace.state import ProjectRecord, TaskStatus


APPROVE_ALIASES = {"批准", "通过", "同意", "可以"}
REVISE_ALIASES = {"驳回", "拒绝"}
STATUS_ALIASES = {"状态", "进度"}
REPLAN_ALIASES = {"重新规划"}
UNSUPPORTED_REPLY = "当前阶段不支持这个操作，请先发送 状态。"
REUSABLE_START_REPLY = "已收到开始开发请求，我会继续当前项目并进入开发流程。"
EARLY_PROJECT_STATUSES = {
    TaskStatus.DISCOVERY,
    TaskStatus.WAIT_HUMAN_REQUIREMENT,
    TaskStatus.PLANNING,
    TaskStatus.WAIT_HUMAN_PLAN,
}


@dataclass(slots=True)
class WechatMessageService:
    manager: WorkspaceManager
    director_router: DirectorRouter
    workflow_service: WorkflowService

    def handle_message(self, *, wecom_user_id: str, message: str, is_group_chat: bool) -> WechatEventResponse:
        normalized = message.strip()
        session = self.manager.get_session(wecom_user_id)
        reusable_project = self._get_reusable_active_project_for_start(
            normalized,
            session_active_project_id=session.active_project_id if session is not None else None,
        )
        if reusable_project is not None:
            return WechatEventResponse(
                action=DirectorAction.START_PROJECT.value,
                reply=REUSABLE_START_REPLY,
                project=self._to_project_response(reusable_project),
                project_id=reusable_project.id,
            )

        if normalized in APPROVE_ALIASES:
            return self._apply_checkpoint_action(
                session_active_project_id=session.active_project_id if session is not None else None,
                action="approve",
                reply="已批准，流程已进入下一阶段。",
            )

        if normalized in REVISE_ALIASES:
            return self._apply_checkpoint_action(
                session_active_project_id=session.active_project_id if session is not None else None,
                action="revise",
                reply="已打回，流程将回到修改阶段。",
            )

        if normalized in REPLAN_ALIASES:
            return self._handle_replan(session_active_project_id=session.active_project_id if session is not None else None)

        if normalized in STATUS_ALIASES and session is not None and session.active_project_id is not None:
            project = self.manager.get_project(session.active_project_id)
            if project is None:
                return WechatEventResponse(action="chat_reply", reply="当前没有进行中的项目。")
            return WechatEventResponse(
                action=DirectorAction.PROJECT_QUERY.value,
                reply=f"当前项目处于 {project.status.value}。",
                project=self._to_project_response(project),
                project_id=project.id,
            )

        requirement_follow_up = self._handle_requirement_follow_up(
            message=normalized,
            session_active_project_id=session.active_project_id if session is not None else None,
        )
        if requirement_follow_up is not None:
            return requirement_follow_up

        decision = self.director_router.route_message(normalized, session=session, is_group_chat=is_group_chat)
        if decision.conversation_summary is not None or decision.requirement_draft is not None:
            session = self.manager.upsert_chat_session(
                wecom_user_id,
                conversation_summary=decision.conversation_summary,
                requirement_draft=decision.requirement_draft,
            )
            self._refresh_active_early_project(
                session_active_project_id=session.active_project_id if session is not None else None,
                requirement_draft=decision.requirement_draft,
            )

        if decision.action is DirectorAction.START_PROJECT:
            draft_requirement = decision.requirement_draft or (session.last_requirement_draft if session is not None else None)
            requirement = draft_requirement or normalized
            title = draft_requirement or normalized
            project = self.manager.create_project(title=title, requirement=requirement)
            self.manager.bind_active_project(wecom_user_id, project.id)
            return WechatEventResponse(
                action=decision.action.value,
                reply=decision.message,
                project=self._to_project_response(project),
                project_id=project.id,
            )
        if decision.action is DirectorAction.PROJECT_QUERY:
            return WechatEventResponse(
                action=decision.action.value,
                reply=decision.message,
                project_id=decision.project_id,
            )
        return WechatEventResponse(action=decision.action.value, reply=decision.message)

    def _apply_checkpoint_action(self, *, session_active_project_id: str | None, action: str, reply: str) -> WechatEventResponse:
        if session_active_project_id is None:
            return WechatEventResponse(action="chat_reply", reply="当前没有进行中的项目。")
        project = self.manager.get_project(session_active_project_id)
        if project is None or project.current_checkpoint_id is None:
            return WechatEventResponse(action="chat_reply", reply="当前没有待确认的阶段。")
        checkpoint = self.manager.get_checkpoint(project.current_checkpoint_id)
        if checkpoint is None or checkpoint.status != "pending":
            return WechatEventResponse(action="chat_reply", reply="当前没有待确认的阶段。")
        updated_project, _ = self.workflow_service.apply_feedback(
            project_id=project.id,
            checkpoint_id=checkpoint.id,
            checkpoint_type=checkpoint.type,
            action=action,
            comments="",
            rejection_reason_type=None,
            client_version=project.version,
        )
        return WechatEventResponse(
            action="chat_reply",
            reply=reply,
            project=self._to_project_response(updated_project),
            project_id=updated_project.id,
        )

    def _handle_requirement_follow_up(
        self,
        *,
        message: str,
        session_active_project_id: str | None,
    ) -> WechatEventResponse | None:
        if session_active_project_id is None or "开始开发" in message:
            return None
        project = self.manager.get_project(session_active_project_id)
        if project is None or project.status is not TaskStatus.WAIT_HUMAN_REQUIREMENT:
            return None
        if project.current_checkpoint_id is None:
            return None
        checkpoint = self.manager.get_checkpoint(project.current_checkpoint_id)
        if checkpoint is None or checkpoint.status != "pending" or checkpoint.type != "requirement_review":
            return None
        updated_project, _ = self.workflow_service.continue_requirement_discovery(
            project_id=project.id,
            clarification=message,
        )
        return WechatEventResponse(
            action="chat_reply",
            reply=self.workflow_service.requirement_review_reply(updated_project.id),
            project=self._to_project_response(updated_project),
            project_id=updated_project.id,
        )

    def _handle_replan(self, *, session_active_project_id: str | None) -> WechatEventResponse:
        if session_active_project_id is None:
            return WechatEventResponse(action="chat_reply", reply="当前没有进行中的项目。")
        project = self.manager.get_project(session_active_project_id)
        if project is None or project.current_checkpoint_id is None:
            return WechatEventResponse(action="chat_reply", reply="当前没有待确认的阶段。")
        checkpoint = self.manager.get_checkpoint(project.current_checkpoint_id)
        if checkpoint is None or checkpoint.status != "pending" or checkpoint.type != "code_review":
            return WechatEventResponse(action="chat_reply", reply=UNSUPPORTED_REPLY)
        updated_project, _ = self.workflow_service.apply_feedback(
            project_id=project.id,
            checkpoint_id=checkpoint.id,
            checkpoint_type=checkpoint.type,
            action="replan",
            comments="",
            rejection_reason_type=None,
            client_version=project.version,
        )
        return WechatEventResponse(
            action="chat_reply",
            reply="已退回到重新规划阶段。",
            project=self._to_project_response(updated_project),
            project_id=updated_project.id,
        )



    def _get_reusable_active_project_for_start(
        self,
        message: str,
        *,
        session_active_project_id: str | None,
    ) -> ProjectRecord | None:
        if session_active_project_id is None or "开始开发" not in message:
            return None
        project = self.manager.get_project(session_active_project_id)
        if project is None:
            return None
        if project.status is not TaskStatus.DISCOVERY:
            return None
        if project.current_checkpoint_id is not None:
            return None
        return project

    def _refresh_active_early_project(self, *, session_active_project_id: str | None, requirement_draft: str | None) -> None:
        if session_active_project_id is None or requirement_draft is None:
            return
        project = self.manager.get_project(session_active_project_id)
        if project is None or project.status not in EARLY_PROJECT_STATUSES:
            return
        self.manager.refresh_active_project_requirement(
            session_active_project_id,
            title=requirement_draft,
            requirement=requirement_draft,
        )

    @staticmethod
    def _to_project_response(project: ProjectRecord) -> ProjectResponse:
        return ProjectResponse(
            id=project.id,
            title=project.title,
            requirement=project.requirement,
            status=project.status.value,
            version=project.version,
            current_checkpoint_id=project.current_checkpoint_id,
            requires_human_takeover=project.requires_human_takeover,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )
