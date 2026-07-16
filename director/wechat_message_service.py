from __future__ import annotations

from dataclasses import dataclass

from api.schemas import ProjectResponse, WechatEventResponse
from director.agent import DirectorSystemCommand, DirectorTurn
from director.router import DirectorRouter
from graph.runtime import WorkflowService
from workspace.manager import WorkspaceManager
from workspace.state import ProjectRecord, TaskStatus


UNSUPPORTED_REPLY = "当前阶段不支持这个操作，请先发送 状态。"
REUSABLE_START_REPLY = "已收到开始开发请求，我会继续当前项目并进入开发流程。"
EARLY_PROJECT_STATUSES = {
    TaskStatus.DISCOVERY,
    TaskStatus.WAIT_HUMAN_REQUIREMENT,
    TaskStatus.PLANNING,
    TaskStatus.WAIT_HUMAN_PLAN,
}

STAGE_OWNED_STATUSES = {
    TaskStatus.WAIT_HUMAN_REQUIREMENT,
    TaskStatus.WAIT_HUMAN_PLAN,
}
EXPLICIT_CHECKPOINT_COMMANDS = {
    'approve': {'批准', '通过', 'approve'},
    'revise': {'驳回', '打回', 'revise'},
    'replan': {'重新规划', 'replan'},
}


@dataclass(slots=True)
class WechatMessageService:
    manager: WorkspaceManager
    director_router: DirectorRouter
    workflow_service: WorkflowService

    def handle_message(self, *, wecom_user_id: str, message: str, is_group_chat: bool) -> WechatEventResponse:
        normalized = message.strip()
        session = self.manager.get_session(wecom_user_id)

        project_memory = None
        if session is not None and session.active_project_id is not None:
            project_memory = self.manager.read_project_memory(session.active_project_id) or None
        project_context = self._build_project_context(wecom_user_id=wecom_user_id, session=session)

        system_turn = self.director_router.route_system_message(
            normalized,
            session=session,
            project_context=project_context,
        )
        if system_turn is not None:
            return self._handle_system_turn(wecom_user_id=wecom_user_id, turn=system_turn)

        checkpoint_response = self._handle_explicit_checkpoint_command(
            message=normalized,
            session_active_project_id=session.active_project_id if session is not None else None,
        )
        if checkpoint_response is not None:
            return checkpoint_response

        stage_follow_up = self._handle_stage_follow_up(
            message=normalized,
            session_active_project_id=session.active_project_id if session is not None else None,
        )
        if stage_follow_up is not None:
            return stage_follow_up

        turn = self.director_router.route_message(
            normalized,
            session=session,
            is_group_chat=is_group_chat,
            project_memory=project_memory,
            project_context=project_context,
        )

        requirement_draft = turn.requirement_draft
        should_refresh_session = turn.conversation_summary is not None or requirement_draft is not None
        if should_refresh_session:
            session = self.manager.upsert_chat_session(
                wecom_user_id,
                conversation_summary=turn.conversation_summary,
                requirement_draft=requirement_draft,
            )
            self._refresh_active_early_project(
                session_active_project_id=session.active_project_id if session is not None else None,
                requirement_draft=turn.requirement_draft,
            )

        if turn.ready_to_start:
            reusable_project = self._get_reusable_active_project_for_start(
                normalized,
                session_active_project_id=session.active_project_id if session is not None else None,
            )
            if reusable_project is not None:
                if turn.requirement_draft:
                    self.manager.refresh_active_project_requirement(
                        reusable_project.id,
                        title=turn.requirement_draft,
                        requirement=turn.requirement_draft,
                    )
                    reusable_project = self.manager.get_project(reusable_project.id) or reusable_project
                project, checkpoint = self._ensure_project_workflow_started(reusable_project)
                reply = self._project_start_reply(project, checkpoint, turn.message)
                return WechatEventResponse(
                    action='start_project',
                    reply=reply,
                    project=self._to_project_response(project),
                    project_id=project.id,
                )

            requirement = (turn.requirement_draft or (session.last_requirement_draft if session is not None else None) or normalized).strip()
            title = turn.requirement_draft or requirement
            project = self.manager.create_project(title=title, requirement=requirement, owner_wecom_user_id=wecom_user_id)
            self.manager.bind_active_project(wecom_user_id, project.id)
            self.manager.upsert_chat_session(
                wecom_user_id,
                conversation_summary=turn.conversation_summary,
                requirement_draft=turn.requirement_draft,
            )
            project, checkpoint = self._ensure_project_workflow_started(project)
            reply = self._project_start_reply(project, checkpoint, turn.message)
            return WechatEventResponse(
                action='start_project',
                reply=reply,
                project=self._to_project_response(project),
                project_id=project.id,
            )

        return WechatEventResponse(action='chat_reply', reply=turn.message)


    def _handle_system_turn(self, *, wecom_user_id: str, turn: DirectorTurn) -> WechatEventResponse:
        command = turn.system_command
        if command is DirectorSystemCommand.RESET_SESSION:
            self.manager.reset_chat_session(wecom_user_id)
            return WechatEventResponse(action='chat_reply', reply=turn.message)
        if command is DirectorSystemCommand.LIST_PROJECTS:
            return WechatEventResponse(action='chat_reply', reply=self._list_projects_reply(wecom_user_id))
        if command is DirectorSystemCommand.SWITCH_PROJECT:
            return self._handle_switch_project(wecom_user_id=wecom_user_id, target=turn.target)
        if command is DirectorSystemCommand.DELETE_PROJECT:
            return self._handle_delete_project(wecom_user_id=wecom_user_id, target=turn.target)
        if command is DirectorSystemCommand.STATUS:
            return WechatEventResponse(action='project_query', reply=turn.message, project_id=turn.target)
        return WechatEventResponse(action='chat_reply', reply=turn.message)


    def _handle_explicit_checkpoint_command(
        self,
        *,
        message: str,
        session_active_project_id: str | None,
    ) -> WechatEventResponse | None:
        normalized = message.strip().lower()
        if normalized in {item.lower() for item in EXPLICIT_CHECKPOINT_COMMANDS['approve']}:
            return self._apply_checkpoint_action(
                session_active_project_id=session_active_project_id,
                action='approve',
                reply='已批准，流程已进入下一阶段。',
            )
        if normalized in {item.lower() for item in EXPLICIT_CHECKPOINT_COMMANDS['revise']}:
            return self._apply_checkpoint_action(
                session_active_project_id=session_active_project_id,
                action='revise',
                reply='已打回，流程将回到修改阶段。',
            )
        if normalized in {item.lower() for item in EXPLICIT_CHECKPOINT_COMMANDS['replan']}:
            return self._handle_replan(session_active_project_id=session_active_project_id)
        return None


    def _build_project_context(self, *, wecom_user_id: str, session) -> dict[str, object]:
        projects = self.manager.list_projects_for_user(wecom_user_id)
        user_projects = [
            {
                'id': project.id,
                'title': project.title,
                'status': project.status.value,
                'current_checkpoint_id': project.current_checkpoint_id,
            }
            for project in projects
        ]
        if session is None or session.active_project_id is None:
            return {
                'active_project': None,
                'checkpoint': None,
                'user_projects': user_projects,
                'available_actions': ['chat_reply', 'start_project', 'reset_session', 'list_projects'],
            }
        project = self.manager.get_project(session.active_project_id)
        checkpoint = self.manager.get_checkpoint(project.current_checkpoint_id) if project is not None and project.current_checkpoint_id else None
        available_actions = ['chat_reply', 'project_query', 'continue_project', 'reset_session', 'list_projects', 'switch_project', 'delete_project']
        if checkpoint is not None and checkpoint.status == 'pending' and checkpoint.type not in {'requirement_review', 'plan_review'}:
            available_actions.append('checkpoint_action')
        return {
            'active_project': {
                'id': project.id if project is not None else session.active_project_id,
                'title': project.title if project is not None else None,
                'status': project.status.value if project is not None else None,
                'current_checkpoint_id': project.current_checkpoint_id if project is not None else None,
            },
            'checkpoint': {
                'id': checkpoint.id,
                'type': checkpoint.type,
                'status': checkpoint.status,
                'available_actions': list(checkpoint.available_actions),
            } if checkpoint is not None else None,
            'user_projects': user_projects,
            'available_actions': available_actions,
        }



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

    def _ensure_project_workflow_started(self, project: ProjectRecord) -> tuple[ProjectRecord, object | None]:
        if project.current_checkpoint_id is not None or project.status is not TaskStatus.DISCOVERY:
            return project, self.manager.get_checkpoint(project.current_checkpoint_id) if project.current_checkpoint_id else None
        return self.workflow_service.start_project(project.id)

    def _project_start_reply(self, project: ProjectRecord, checkpoint, default_reply: str) -> str:
        if checkpoint is not None:
            return self.workflow_service._checkpoint_message(project.id, checkpoint.type)
        return default_reply


    def _handle_stage_follow_up(
        self,
        *,
        message: str,
        session_active_project_id: str | None,
    ) -> WechatEventResponse | None:
        if session_active_project_id is None or '开始开发' in message:
            return None
        project = self.manager.get_project(session_active_project_id)
        if project is None or project.status not in STAGE_OWNED_STATUSES:
            return None
        if project.status is TaskStatus.WAIT_HUMAN_REQUIREMENT:
            return self._handle_requirement_follow_up(
                message=message,
                session_active_project_id=session_active_project_id,
            )
        if project.status is TaskStatus.WAIT_HUMAN_PLAN:
            return self._handle_plan_follow_up(
                message=message,
                session_active_project_id=session_active_project_id,
            )
        return None





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
        updated_project, next_checkpoint, direct_reply = self.workflow_service.continue_requirement_discovery(
            project_id=project.id,
            clarification=message,
        )
        if direct_reply is not None:
            reply = direct_reply
        elif next_checkpoint is not None:
            reply = self.workflow_service._checkpoint_message(updated_project.id, next_checkpoint.type)
        else:
            reply = self.workflow_service.requirement_review_reply(updated_project.id)
        return WechatEventResponse(
            action="chat_reply",
            reply=reply,
            project=self._to_project_response(updated_project),
            project_id=updated_project.id,
        )


    def _handle_plan_follow_up(
        self,
        *,
        message: str,
        session_active_project_id: str | None,
    ) -> WechatEventResponse | None:
        if session_active_project_id is None or '开始开发' in message:
            return None
        project = self.manager.get_project(session_active_project_id)
        if project is None or project.status is not TaskStatus.WAIT_HUMAN_PLAN:
            return None
        if project.current_checkpoint_id is None:
            return None
        checkpoint = self.manager.get_checkpoint(project.current_checkpoint_id)
        if checkpoint is None or checkpoint.status != 'pending' or checkpoint.type != 'plan_review':
            return None
        updated_project, next_checkpoint, direct_reply = self.workflow_service.continue_plan_review(
            project_id=project.id,
            user_reply=message,
        )
        if direct_reply is not None:
            reply = direct_reply
        elif next_checkpoint is not None:
            reply = self.workflow_service._checkpoint_message(updated_project.id, next_checkpoint.type)
        else:
            reply = self.workflow_service.plan_review_reply(updated_project.id)
        return WechatEventResponse(
            action='chat_reply',
            reply=reply,
            project=self._to_project_response(updated_project),
            project_id=updated_project.id,
        )

    def _list_projects_reply(self, wecom_user_id: str) -> str:
        projects = self.manager.list_projects_for_user(wecom_user_id)
        if not projects:
            return "当前没有可管理的历史项目。"
        session = self.manager.get_session(wecom_user_id)
        active_project_id = session.active_project_id if session is not None else None
        lines = ["你的项目列表："]
        for index, project in enumerate(projects, start=1):
            marker = " [当前]" if project.id == active_project_id else ""
            lines.append(f"{index}. {project.title[:30]}{marker} | {project.status.value} | {project.id[:8]}")
        lines.append("发送 `切换项目 序号` 或 `删除项目 序号` 继续操作。")
        return "\n".join(lines)

    def _handle_switch_project(self, *, wecom_user_id: str, target: str | None) -> WechatEventResponse:
        if not target:
            return WechatEventResponse(action="chat_reply", reply="请发送 `切换项目 序号`。")
        project = self._resolve_user_project(wecom_user_id, target)
        if project is None:
            return WechatEventResponse(action="chat_reply", reply="未找到对应项目，请先发送 `我的项目` 查看序号。")
        self.manager.switch_active_project(wecom_user_id, project.id)
        updated = self.manager.get_project(project.id)
        return WechatEventResponse(
            action="chat_reply",
            reply=f"已切换到项目：{project.title}，当前状态为 {project.status.value}。",
            project=self._to_project_response(updated or project),
            project_id=project.id,
        )

    def _handle_delete_project(self, *, wecom_user_id: str, target: str | None) -> WechatEventResponse:
        if not target:
            return WechatEventResponse(action="chat_reply", reply="请发送 `删除项目 序号`。")
        project = self._resolve_user_project(wecom_user_id, target)
        if project is None:
            return WechatEventResponse(action="chat_reply", reply="未找到对应项目，请先发送 `我的项目` 查看序号。")
        self.manager.delete_project(project.id)
        return WechatEventResponse(
            action="chat_reply",
            reply=f"已删除项目：{project.title}。",
        )

    def _resolve_user_project(self, wecom_user_id: str, target: str) -> ProjectRecord | None:
        projects = self.manager.list_projects_for_user(wecom_user_id)
        if target.isdigit():
            index = int(target)
            if 1 <= index <= len(projects):
                return projects[index - 1]
            return None
        matches = [project for project in projects if project.id.startswith(target)]
        if len(matches) == 1:
            return matches[0]
        return None

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
