from __future__ import annotations

import json

from dataclasses import dataclass, field
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from agents.coder import CoderAgent
from agents.debugger import DebuggerAgent
from agents.planner import PlannerAgent
from agents.pm import PMAgent
from agents.reviewer import ReviewerAgent
from graph.builder import build_development_graph
from notifications.publisher import NoopNotificationPublisher, NotificationPublisher
from tools.sandbox import DockerSandbox
from workspace.manager import WorkspaceManager
from workspace.state import CheckpointRecord, ProjectRecord, TaskStatus


class FeedbackConflictError(RuntimeError):
    """Raised when feedback does not match the current pending checkpoint."""


@dataclass(slots=True)
class WorkflowService:
    manager: WorkspaceManager
    pm_agent: object = field(default_factory=PMAgent)
    planner_agent: object = field(default_factory=PlannerAgent)
    coder_agent: object = field(default_factory=CoderAgent)
    debugger_agent: object = field(default_factory=DebuggerAgent)
    reviewer_agent: object = field(default_factory=ReviewerAgent)
    sandbox: object = field(default_factory=DockerSandbox)
    checkpointer: InMemorySaver = field(default_factory=InMemorySaver)
    notification_publisher: NotificationPublisher = field(default_factory=NoopNotificationPublisher)
    graph: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.graph = build_development_graph(
            pm_agent=self.pm_agent,
            planner_agent=self.planner_agent,
            coder_agent=self.coder_agent,
            debugger_agent=self.debugger_agent,
            sandbox=self.sandbox,
            checkpointer=self.checkpointer,
        )

    def start_project(self, project_id: str) -> tuple[ProjectRecord, CheckpointRecord | None]:
        project, checkpoint, _ = self._run_discovery(
            project_id,
            publish_started=True,
            publish_follow_up=True,
        )
        return project, checkpoint

    def continue_requirement_discovery(self, *, project_id: str, clarification: str) -> tuple[ProjectRecord, CheckpointRecord | None]:
        project = self.manager.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        updated_requirement = self._merge_requirement(project.requirement, clarification)
        self.manager.refresh_active_project_requirement(
            project_id,
            title=project.title,
            requirement=updated_requirement,
        )
        project, checkpoint, _ = self._run_discovery(
            project_id,
            publish_started=False,
            publish_follow_up=False,
            extra_conversation=[{"role": "user_clarification", "content": clarification}],
        )
        return project, checkpoint

    def apply_feedback(self, *, project_id: str, checkpoint_id: str, checkpoint_type: str, action: str, comments: str, rejection_reason_type: str | None, client_version: int) -> tuple[ProjectRecord, CheckpointRecord | None]:
        project = self.manager.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        if project.version != client_version:
            raise FeedbackConflictError('project version conflict')
        if project.current_checkpoint_id != checkpoint_id:
            raise FeedbackConflictError('checkpoint does not match current project state')
        checkpoint = self.manager.get_checkpoint(checkpoint_id)
        if checkpoint is None or checkpoint.status != 'pending':
            raise FeedbackConflictError('checkpoint is not pending')
        if checkpoint.type != checkpoint_type:
            raise FeedbackConflictError('checkpoint type mismatch')

        wecom_user_id = self.manager.find_wecom_user_id_by_project(project_id)
        snapshot = self.graph.get_state(self._config(project_id))
        state = dict(snapshot.values)

        if checkpoint_type == 'requirement_review':
            status_value, next_checkpoint = self._apply_requirement_feedback(project_id, state, action)
        elif checkpoint_type == 'plan_review':
            status_value, next_checkpoint = self._apply_plan_feedback(project_id, state, action)
        elif checkpoint_type == 'code_review':
            status_value, next_checkpoint = self._apply_code_feedback(project_id, state, action)
        elif checkpoint_type == 'final_review':
            status_value, next_checkpoint = self._apply_final_feedback(project_id, action, rejection_reason_type)
        else:
            raise FeedbackConflictError('unsupported checkpoint type')

        self.manager.resolve_checkpoint(checkpoint_id)
        project = self.manager.update_project_flow_state(
            project_id,
            status=status_value,
            current_checkpoint_id=next_checkpoint.id if next_checkpoint else None,
        )
        self._publish_follow_up_notification(project, next_checkpoint, wecom_user_id)
        return project, next_checkpoint

    def _apply_requirement_feedback(self, project_id: str, state: dict[str, Any], action: str) -> tuple[TaskStatus, CheckpointRecord | None]:
        if action == 'approve':
            plan = self.planner_agent.run(state['requirement_spec'])
            self.graph.update_state(self._config(project_id), {'plan': plan, 'current_task': TaskStatus.WAIT_HUMAN_PLAN})
            checkpoint = self._create_checkpoint_for_task(project_id, TaskStatus.WAIT_HUMAN_PLAN)
            return TaskStatus.WAIT_HUMAN_PLAN, checkpoint
        if action == 'revise':
            self.graph.update_state(self._config(project_id), {'current_task': TaskStatus.DISCOVERY})
            return TaskStatus.DISCOVERY, None
        self.graph.update_state(self._config(project_id), {'current_task': TaskStatus.CANCELLED})
        return TaskStatus.CANCELLED, None

    def _apply_plan_feedback(self, project_id: str, state: dict[str, Any], action: str) -> tuple[TaskStatus, CheckpointRecord | None]:
        if action == 'revise':
            self.graph.update_state(self._config(project_id), {'current_task': TaskStatus.PLANNING})
            return TaskStatus.PLANNING, None
        if action != 'approve':
            self.graph.update_state(self._config(project_id), {'current_task': TaskStatus.CANCELLED})
            return TaskStatus.CANCELLED, None

        code_result = self.coder_agent.run(plan=state['plan'], current_files=state.get('code_files') or {}, task_description=str(state['plan']['summary']))
        code_files = self._normalize_code_files(code_result.get('modified_files', {}))
        self.manager.persist_code_files(project_id, code_files)
        debug_summary = None
        test_results = self.sandbox.run_tests(code_files)
        while test_results.get('status') == 'failed' and test_results.get('failure_type') in {'runtime_error', 'assertion_failure'}:
            debug_result = self.debugger_agent.run(code_files=code_files, test_results=test_results, error_log=test_results.get('raw_logs'))
            code_files.update(self._normalize_code_files(debug_result.get('patches', {})))
            self.manager.persist_code_files(project_id, code_files)
            debug_summary = debug_result.get('diagnosis', '')
            test_results = self.sandbox.run_tests(code_files)

        if test_results.get('status') == 'passed':
            self.graph.update_state(self._config(project_id), {'code_files': code_files, 'test_results': test_results, 'debug_summary': debug_summary, 'current_task': TaskStatus.WAIT_HUMAN_CODE})
            checkpoint = self._create_checkpoint_for_task(project_id, TaskStatus.WAIT_HUMAN_CODE)
            return TaskStatus.WAIT_HUMAN_CODE, checkpoint

        failure_type = test_results.get('failure_type')
        fallback_status = TaskStatus.CODING if failure_type in {'static_check', 'build_error'} else TaskStatus.FAILED
        self.graph.update_state(self._config(project_id), {'code_files': code_files, 'test_results': test_results, 'debug_summary': debug_summary, 'current_task': fallback_status})
        return fallback_status, None

    def _apply_code_feedback(self, project_id: str, state: dict[str, Any], action: str) -> tuple[TaskStatus, CheckpointRecord | None]:
        if action == 'replan':
            self.graph.update_state(self._config(project_id), {'current_task': TaskStatus.PLANNING})
            return TaskStatus.PLANNING, None
        if action == 'revise':
            self.graph.update_state(self._config(project_id), {'current_task': TaskStatus.CODING})
            return TaskStatus.CODING, None
        review_report = self.reviewer_agent.run(plan=state['plan'], code_files=state.get('code_files') or {}, test_results=state.get('test_results') or {})
        self.graph.update_state(self._config(project_id), {'review_report': review_report, 'current_task': TaskStatus.WAIT_HUMAN_FINAL})
        checkpoint = self._create_checkpoint_for_task(project_id, TaskStatus.WAIT_HUMAN_FINAL)
        return TaskStatus.WAIT_HUMAN_FINAL, checkpoint

    def _apply_final_feedback(self, project_id: str, action: str, rejection_reason_type: str | None) -> tuple[TaskStatus, CheckpointRecord | None]:
        if action == 'approve':
            self.graph.update_state(self._config(project_id), {'current_task': TaskStatus.DONE})
            return TaskStatus.DONE, None
        if action == 'revise':
            if rejection_reason_type == 'plan_issue':
                next_status = TaskStatus.PLANNING
            elif rejection_reason_type == 'execution_issue':
                next_status = TaskStatus.DEBUGGING
            else:
                next_status = TaskStatus.CODING
            self.graph.update_state(self._config(project_id), {'current_task': next_status})
            return next_status, None
        self.graph.update_state(self._config(project_id), {'current_task': TaskStatus.CANCELLED})
        return TaskStatus.CANCELLED, None

    def requirement_review_reply(self, project_id: str) -> str:
        questions = self._requirement_open_questions(project_id)
        if questions:
            lines = ["PM 还需要确认这些问题："]
            lines.extend(f"{index}. {question}" for index, question in enumerate(questions, start=1))
            lines.append("请直接回复补充信息；信息足够时也可以回复 批准 / 可以。")
            return "\n".join(lines)
        return "PM 已整理出需求草案，请确认需求。回复 批准 / 可以 继续，或继续补充需求。"

    def _run_discovery(
        self,
        project_id: str,
        *,
        publish_started: bool,
        publish_follow_up: bool,
        extra_conversation: list[dict[str, str]] | None = None,
    ) -> tuple[ProjectRecord, CheckpointRecord | None, dict[str, Any]]:
        project = self.manager.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        wecom_user_id = self.manager.find_wecom_user_id_by_project(project_id)
        config = self._config(project_id)
        result = self.graph.invoke(
            {
                'requirement': project.requirement,
                'conversation': self._build_requirement_conversation(project_id, extra_conversation=extra_conversation),
            },
            config=config,
        )
        checkpoint = self._create_checkpoint_for_task(project_id, result['current_task'])
        project = self.manager.update_project_flow_state(
            project_id,
            status=result['current_task'],
            current_checkpoint_id=checkpoint.id if checkpoint else None,
        )
        if wecom_user_id is not None and publish_started:
            self._publish_event(
                event_type='project_started',
                project_id=project.id,
                wecom_user_id=wecom_user_id,
                message='项目已启动，流程正在推进。',
                status=project.status.value,
            )
        if wecom_user_id is not None and publish_follow_up:
            self._publish_follow_up_notification(project, checkpoint, wecom_user_id)
        return project, checkpoint, result

    def _build_requirement_conversation(
        self,
        project_id: str,
        *,
        extra_conversation: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        conversation: list[dict[str, str]] = []
        wecom_user_id = self.manager.find_wecom_user_id_by_project(project_id)
        if wecom_user_id is not None:
            session = self.manager.get_session(wecom_user_id)
            if session is not None:
                if session.conversation_summary:
                    conversation.append({'role': 'director_summary', 'content': session.conversation_summary})
                if session.last_requirement_draft:
                    conversation.append({'role': 'director_draft', 'content': session.last_requirement_draft})
        if extra_conversation:
            conversation.extend(extra_conversation)
        return conversation

    def _requirement_open_questions(self, project_id: str) -> list[str]:
        snapshot = self.graph.get_state(self._config(project_id))
        requirement_spec = snapshot.values.get('requirement_spec') or {}
        questions = requirement_spec.get('open_questions') or []
        return [str(question).strip() for question in questions if str(question).strip()]


    @classmethod
    def _normalize_code_files(cls, code_files: object) -> dict[str, str]:
        if not isinstance(code_files, dict):
            return {}
        normalized: dict[str, str] = {}
        for relative_path, content in code_files.items():
            normalized[str(relative_path)] = cls._stringify_file_content(content)
        return normalized

    @staticmethod
    def _stringify_file_content(content: object) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            for key in ('content', 'text', 'code', 'source'):
                value = content.get(key)
                if isinstance(value, str):
                    return value
            return json.dumps(content, ensure_ascii=False)
        if isinstance(content, list):
            return json.dumps(content, ensure_ascii=False)
        if content is None:
            return ''
        return str(content)

    @staticmethod
    def _merge_requirement(requirement: str, clarification: str) -> str:
        base = requirement.rstrip()
        extra = clarification.strip()
        if not extra:
            return base
        if not base:
            return extra
        return f"{base}\n\n补充说明：{extra}"

    @staticmethod
    def _config(project_id: str) -> dict[str, dict[str, str]]:
        return {'configurable': {'thread_id': project_id}}

    def _create_checkpoint_for_task(self, project_id: str, task: TaskStatus) -> CheckpointRecord | None:
        if task is TaskStatus.WAIT_HUMAN_REQUIREMENT:
            return self.manager.create_checkpoint(project_id=project_id, checkpoint_type='requirement_review', available_actions=['approve', 'revise', 'reject', 'pause'])
        if task is TaskStatus.WAIT_HUMAN_PLAN:
            return self.manager.create_checkpoint(project_id=project_id, checkpoint_type='plan_review', available_actions=['approve', 'revise', 'reject', 'pause'])
        if task is TaskStatus.WAIT_HUMAN_CODE:
            return self.manager.create_checkpoint(project_id=project_id, checkpoint_type='code_review', available_actions=['approve', 'revise', 'replan', 'pause'])
        if task is TaskStatus.WAIT_HUMAN_FINAL:
            return self.manager.create_checkpoint(project_id=project_id, checkpoint_type='final_review', available_actions=['approve', 'revise', 'reject', 'pause'])
        return None

    def _publish_follow_up_notification(
        self,
        project: ProjectRecord,
        next_checkpoint: CheckpointRecord | None,
        wecom_user_id: str | None,
    ) -> None:
        if wecom_user_id is None:
            return
        if next_checkpoint is not None:
            self._publish_event(
                event_type='checkpoint_ready',
                project_id=project.id,
                wecom_user_id=wecom_user_id,
                message=self._checkpoint_message(project.id, next_checkpoint.type),
                status=project.status.value,
                checkpoint_type=next_checkpoint.type,
            )
            return
        if project.status is TaskStatus.DONE:
            self._publish_event(
                event_type='project_completed',
                project_id=project.id,
                wecom_user_id=wecom_user_id,
                message='项目已完成，请查看结果。',
                status=project.status.value,
            )
            return
        if project.status is TaskStatus.FAILED:
            self._publish_event(
                event_type='project_failed',
                project_id=project.id,
                wecom_user_id=wecom_user_id,
                message='项目执行失败，请稍后重试。',
                status=project.status.value,
            )

    def _publish_event(
        self,
        *,
        event_type: str,
        project_id: str,
        wecom_user_id: str,
        message: str,
        status: str,
        checkpoint_type: str | None = None,
    ) -> None:
        try:
            self.notification_publisher.publish_event(
                event_type=event_type,
                project_id=project_id,
                wecom_user_id=wecom_user_id,
                message=message,
                status=status,
                checkpoint_type=checkpoint_type,
            )
        except Exception:
            return

    def _checkpoint_message(self, project_id: str, checkpoint_type: str) -> str:
        if checkpoint_type == 'requirement_review':
            return self.requirement_review_reply(project_id)
        if checkpoint_type == 'plan_review':
            return '需求已确认，请审核计划。'
        if checkpoint_type == 'code_review':
            return '开发与测试已完成，请审核代码结果。'
        if checkpoint_type == 'final_review':
            return '代码审查已完成，请进行最终审批。'
        return '项目有新的待处理阶段，请查看。'
