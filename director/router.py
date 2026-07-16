from __future__ import annotations

import inspect
from typing import Any

from director.agent import DirectorAgent, DirectorSystemCommand, DirectorTurn
from workspace.state import WechatSessionRecord


class UnsupportedConversationError(RuntimeError):
    """Raised when the conversation type is outside the MVP scope."""



class DirectorRouter:
    def __init__(self, agent: DirectorAgent | None = None) -> None:
        self.agent = agent

    def route_system_message(
        self,
        message: str,
        session: WechatSessionRecord | None = None,
        *,
        project_context: dict[str, Any] | None = None,
    ) -> DirectorTurn | None:
        normalized = message.strip()
        if normalized == '新会话':
            return DirectorTurn(message='已开启新会话，当前不再绑定旧项目。', system_command=DirectorSystemCommand.RESET_SESSION)
        if normalized == '我的项目':
            return DirectorTurn(message='我来列出项目。', system_command=DirectorSystemCommand.LIST_PROJECTS)
        if normalized == '状态':
            return self._project_status_turn(session=session, project_context=project_context)
        if normalized.startswith('切换项目'):
            return DirectorTurn(
                message='切换到指定项目。',
                system_command=DirectorSystemCommand.SWITCH_PROJECT,
                target=self._extract_command_target(normalized, '切换项目'),
            )
        if normalized.startswith('删除项目'):
            return DirectorTurn(
                message='删除指定项目。',
                system_command=DirectorSystemCommand.DELETE_PROJECT,
                target=self._extract_command_target(normalized, '删除项目'),
            )
        return None

    def route_message(
        self,
        message: str,
        session: WechatSessionRecord | None = None,
        *,
        is_group_chat: bool = False,
        project_memory: str | None = None,
        project_context: dict[str, Any] | None = None,
    ) -> DirectorTurn:
        normalized = message.strip()
        if is_group_chat:
            raise UnsupportedConversationError('group chat is not supported in MVP')
        explicit = self.route_system_message(normalized, session=session, project_context=project_context)
        if explicit is not None:
            return explicit
        if self.agent is not None and self._should_use_agent():
            run_signature = inspect.signature(self.agent.run)
            kwargs: dict[str, Any] = {'session': session}
            if 'project_memory' in run_signature.parameters:
                kwargs['project_memory'] = project_memory
            if 'project_context' in run_signature.parameters:
                kwargs['project_context'] = project_context
            return self.agent.run(normalized, **kwargs)
        return DirectorTurn(message='我先继续和你澄清需求，不会自动进入开发流程。')

    @staticmethod
    def _extract_command_target(message: str, prefix: str) -> str | None:
        target = message[len(prefix):].strip()
        return target or None

    @staticmethod
    def _project_status_turn(
        *,
        session: WechatSessionRecord | None,
        project_context: dict[str, Any] | None,
    ) -> DirectorTurn:
        active_project = project_context.get('active_project') if isinstance(project_context, dict) else None
        if not isinstance(active_project, dict):
            return DirectorTurn(
                message='当前没有进行中的项目。',
                system_command=DirectorSystemCommand.STATUS,
                target=session.active_project_id if session is not None else None,
            )
        project_id = active_project.get('id')
        title = str(active_project.get('title') or project_id or '当前项目')
        status = str(active_project.get('status') or 'unknown')
        reply = f'当前项目：{title}，状态：{status}。'
        checkpoint = project_context.get('checkpoint') if isinstance(project_context, dict) else None
        if isinstance(checkpoint, dict):
            checkpoint_type = checkpoint.get('type')
            checkpoint_status = checkpoint.get('status')
            if checkpoint_type and checkpoint_status:
                reply += f' 当前检查点：{checkpoint_type}（{checkpoint_status}）。'
        return DirectorTurn(
            message=reply,
            system_command=DirectorSystemCommand.STATUS,
            target=project_id if isinstance(project_id, str) else None,
        )

    def _should_use_agent(self) -> bool:
        if self.agent is None:
            return False
        if not hasattr(self.agent, 'llm_client'):
            return True
        return getattr(self.agent, 'llm_client') is not None
