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
from observability import trace_span
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
        with trace_span(
            name='workflow.start_project',
            run_type='chain',
            inputs={'project_id': project_id},
            metadata={'project_id': project_id, 'entrypoint': 'start_project'},
            tags=['workflow', 'project'],
        ) as run_tree:
            project, checkpoint, _ = self._run_discovery(
                project_id,
                publish_started=True,
                publish_follow_up=True,
            )
            run_tree.end(
                outputs={
                    'status': project.status.value,
                    'checkpoint_type': checkpoint.type if checkpoint else None,
                }
            )
            return project, checkpoint

    def continue_requirement_discovery(self, *, project_id: str, clarification: str) -> tuple[ProjectRecord, CheckpointRecord | None, str | None]:
        with trace_span(
            name='workflow.continue_requirement_discovery',
            run_type='chain',
            inputs={'project_id': project_id, 'clarification': clarification},
            metadata={'project_id': project_id, 'entrypoint': 'continue_requirement_discovery'},
            tags=['workflow', 'requirement'],
        ) as run_tree:
            project = self.manager.get_project(project_id)
            if project is None:
                raise KeyError(project_id)
            snapshot = self.graph.get_state(self._config(project_id))
            requirement_spec = snapshot.values.get('requirement_spec') or {}
            current_question = self._current_requirement_question(project_id)
            checkpoint = self.manager.get_checkpoint(project.current_checkpoint_id) if project.current_checkpoint_id else None
            requirement_turn_mode = snapshot.values.get('requirement_turn_mode')
            if requirement_turn_mode == 'awaiting_recommendation_confirmation' and self._is_natural_confirmation(clarification):
                decision = {
                    'reply': None,
                    'recommendation': None,
                    'requirement_update': None,
                    'ready_to_advance': True,
                }
            else:
                decision = self._interpret_requirement_reply(
                    requirement_spec=requirement_spec,
                    current_question=current_question,
                    user_reply=clarification,
                )
            if bool(decision.get('ready_to_advance')):
                if project.current_checkpoint_id is None:
                    raise FeedbackConflictError('checkpoint does not match current project state')
                if checkpoint is None:
                    raise FeedbackConflictError('checkpoint is not pending')
                updated_project, next_checkpoint = self.apply_feedback(
                    project_id=project.id,
                    checkpoint_id=checkpoint.id,
                    checkpoint_type=checkpoint.type,
                    action='approve',
                    comments='',
                    rejection_reason_type=None,
                    client_version=project.version,
                )
                run_tree.end(outputs={'status': updated_project.status.value, 'checkpoint_type': next_checkpoint.type if next_checkpoint else None, 'turn_mode': 'ready_to_advance'})
                return updated_project, next_checkpoint, None

            recommendation = str(decision.get('recommendation') or '').strip()
            if recommendation:
                self.graph.update_state(self._config(project_id), {'requirement_turn_mode': 'awaiting_recommendation_confirmation'})
                reply = self.requirement_suggestion_reply(
                    current_question=current_question,
                    recommendation=recommendation,
                )
                run_tree.end(outputs={'status': project.status.value, 'checkpoint_type': checkpoint.type if checkpoint else None, 'turn_mode': 'recommendation'})
                return project, checkpoint, reply

            self.graph.update_state(self._config(project_id), {'requirement_turn_mode': None})
            reply = str(decision.get('reply') or '').strip()
            if reply:
                run_tree.end(outputs={'status': project.status.value, 'checkpoint_type': checkpoint.type if checkpoint else None, 'turn_mode': 'reply'})
                return project, checkpoint, reply

            normalized_clarification = str(decision.get('requirement_update') or '').strip()
            if not normalized_clarification:
                run_tree.end(outputs={'status': project.status.value, 'checkpoint_type': checkpoint.type if checkpoint else None, 'turn_mode': 'no_change'})
                return project, checkpoint, self.requirement_review_reply(project.id)

            updated_requirement = self._merge_requirement(project.requirement, normalized_clarification)
            self.manager.refresh_active_project_requirement(
                project_id,
                title=project.title,
                requirement=updated_requirement,
            )
            project, checkpoint, _ = self._run_discovery(
                project_id,
                publish_started=False,
                publish_follow_up=False,
                extra_conversation=[{"role": "user_clarification", "content": normalized_clarification}],
            )
            run_tree.end(
                outputs={
                    'status': project.status.value,
                    'checkpoint_type': checkpoint.type if checkpoint else None,
                    'turn_mode': 'requirement_update',
                }
            )
            return project, checkpoint, None


    def continue_plan_review(self, *, project_id: str, user_reply: str) -> tuple[ProjectRecord, CheckpointRecord | None, str | None]:
        with trace_span(
            name='workflow.continue_plan_review',
            run_type='chain',
            inputs={'project_id': project_id, 'user_reply': user_reply},
            metadata={'project_id': project_id, 'entrypoint': 'continue_plan_review'},
            tags=['workflow', 'plan_review'],
        ) as run_tree:
            project = self.manager.get_project(project_id)
            if project is None:
                raise KeyError(project_id)
            snapshot = self.graph.get_state(self._config(project_id))
            state = dict(snapshot.values)
            plan = state.get('plan') or {}
            checkpoint = self.manager.get_checkpoint(project.current_checkpoint_id) if project.current_checkpoint_id else None
            decision = self._interpret_plan_reply(plan=plan, user_reply=user_reply)
            if bool(decision.get('ready_to_advance')):
                if project.current_checkpoint_id is None:
                    raise FeedbackConflictError('checkpoint does not match current project state')
                if checkpoint is None:
                    raise FeedbackConflictError('checkpoint is not pending')
                updated_project, next_checkpoint = self.apply_feedback(
                    project_id=project.id,
                    checkpoint_id=checkpoint.id,
                    checkpoint_type=checkpoint.type,
                    action='approve',
                    comments='',
                    rejection_reason_type=None,
                    client_version=project.version,
                )
                run_tree.end(outputs={'status': updated_project.status.value, 'checkpoint_type': next_checkpoint.type if next_checkpoint else None, 'turn_mode': 'ready_to_advance'})
                return updated_project, next_checkpoint, None

            recommendation = str(decision.get('recommendation') or '').strip()
            if recommendation:
                reply = self.plan_suggestion_reply(recommendation=recommendation)
                run_tree.end(outputs={'status': project.status.value, 'checkpoint_type': checkpoint.type if checkpoint else None, 'turn_mode': 'recommendation'})
                return project, checkpoint, reply

            plan_update = str(decision.get('plan_update') or '').strip()
            if plan_update:
                requirement_spec = self._merge_requirement_spec_for_plan_revision(state.get('requirement_spec') or {}, plan_update)
                new_plan = self.planner_agent.run(requirement_spec)
                self.graph.update_state(
                    self._config(project_id),
                    {
                        'requirement_spec': requirement_spec,
                        'plan': new_plan,
                        'current_task': TaskStatus.WAIT_HUMAN_PLAN,
                    },
                )
                if checkpoint is not None and checkpoint.status == 'pending':
                    self.manager.resolve_checkpoint(checkpoint.id)
                next_checkpoint = self._create_checkpoint_for_task(project_id, TaskStatus.WAIT_HUMAN_PLAN)
                project = self.manager.get_project(project_id)
                if project is None:
                    raise KeyError(project_id)
                wecom_user_id = self.manager.find_wecom_user_id_by_project(project_id)
                self._sync_project_memory(project_id, wecom_user_id=wecom_user_id, current_status=project.status)
                self._publish_follow_up_notification(project, next_checkpoint, wecom_user_id)
                run_tree.end(outputs={'status': project.status.value, 'checkpoint_type': next_checkpoint.type if next_checkpoint else None, 'turn_mode': 'plan_update'})
                return project, next_checkpoint, None

            reply = str(decision.get('reply') or '').strip() or self.plan_review_reply(project.id)
            run_tree.end(outputs={'status': project.status.value, 'checkpoint_type': checkpoint.type if checkpoint else None, 'turn_mode': 'reply'})
            return project, checkpoint, reply

    def apply_feedback(self, *, project_id: str, checkpoint_id: str, checkpoint_type: str, action: str, comments: str, rejection_reason_type: str | None, client_version: int) -> tuple[ProjectRecord, CheckpointRecord | None]:
        with trace_span(
            name='workflow.apply_feedback',
            run_type='chain',
            inputs={
                'project_id': project_id,
                'checkpoint_id': checkpoint_id,
                'checkpoint_type': checkpoint_type,
                'action': action,
                'client_version': client_version,
            },
            metadata={'project_id': project_id, 'checkpoint_type': checkpoint_type},
            tags=['workflow', 'feedback'],
        ) as run_tree:
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
            self._sync_project_memory(project_id, wecom_user_id=wecom_user_id, current_status=project.status)
            self._publish_follow_up_notification(project, next_checkpoint, wecom_user_id)
            run_tree.end(
                outputs={
                    'status': project.status.value,
                    'checkpoint_type': next_checkpoint.type if next_checkpoint else None,
                }
            )
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
        test_attempt = 1
        test_results = self._run_tests_with_trace(project_id, code_files, attempt=test_attempt)
        while test_results.get('status') == 'failed' and test_results.get('failure_type') in {'runtime_error', 'assertion_failure'}:
            debug_result = self.debugger_agent.run(code_files=code_files, test_results=test_results, error_log=test_results.get('raw_logs'))
            code_files.update(self._normalize_code_files(debug_result.get('patches', {})))
            self.manager.persist_code_files(project_id, code_files)
            debug_summary = debug_result.get('diagnosis', '')
            test_attempt += 1
            test_results = self._run_tests_with_trace(project_id, code_files, attempt=test_attempt)

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
        snapshot = self.graph.get_state(self._config(project_id))
        requirement_spec = snapshot.values.get('requirement_spec') or {}
        questions = self._requirement_open_questions(project_id)
        lines = ["PM 已完成一轮 brainstorm。"]
        if questions:
            lines.append("我先只确认一个最关键的问题：")
            lines.append(f"1. {questions[0]}")
            lines.append("你直接回答这个问题就行；如果你暂时没想法，也可以回复“你来建议”。")
            return "\n".join(lines)
        lines.append("如果你认可这轮 brainstorm，回复 批准 进入 writing plan。")
        return "\n".join(lines)

    def requirement_suggestion_reply(
        self,
        *,
        current_question: str | None,
        recommendation: str,
    ) -> str:
        lines = ["PM 的建议：", recommendation]
        if current_question:
            lines.append(f"这是针对当前问题「{current_question}」给出的建议。")
        lines.append("如果你认可这个建议，直接确认就行；如果你想换个方向，也可以直接说。")
        return "\n".join(lines)


    def plan_review_reply(self, project_id: str) -> str:
        snapshot = self.graph.get_state(self._config(project_id))
        plan = snapshot.values.get('plan') or {}
        lines = ['Planner 已生成一版 writing plan。']
        summary = str(plan.get('summary') or '').strip()
        if summary:
            lines.append(f'计划概述：{summary}')
        tasks = [str(task).strip() for task in (plan.get('tasks') or []) if str(task).strip()]
        if tasks:
            lines.append('核心步骤：')
            for index, task in enumerate(tasks[:3], start=1):
                lines.append(f'{index}. {task}')
        open_questions = [str(item).strip() for item in (plan.get('open_questions') or []) if str(item).strip()]
        if open_questions:
            lines.append(f'还需确认：{open_questions[0]}')
        lines.append('如果你认可这版计划，直接确认就行；如果你想让我先给建议，也可以回复“你来建议”。')
        return '\n'.join(lines)

    def plan_suggestion_reply(self, *, recommendation: str) -> str:
        lines = ['Planner 的建议：', recommendation]
        lines.append('这是基于当前 writing plan 给出的建议。')
        lines.append('如果你认可这版计划，直接确认就行；如果你想调整范围，也可以直接说。')
        return '\n'.join(lines)

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
        self._sync_project_memory(project_id, wecom_user_id=wecom_user_id, current_status=project.status)
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
        project_memory = self.manager.read_project_memory(project_id).strip()
        if project_memory:
            conversation.append({'role': 'project_memory', 'content': project_memory})
        if extra_conversation:
            conversation.extend(extra_conversation)
        return conversation

    def _sync_project_memory(
        self,
        project_id: str,
        *,
        wecom_user_id: str | None,
        current_status: TaskStatus,
    ) -> None:
        project = self.manager.get_project(project_id)
        if project is None:
            return
        snapshot = self.graph.get_state(self._config(project_id))
        state = dict(snapshot.values)
        requirement_spec = state.get('requirement_spec') or {}
        plan = state.get('plan') or {}
        review_report = state.get('review_report') or {}
        test_results = state.get('test_results') or {}
        session = self.manager.get_session(wecom_user_id) if wecom_user_id is not None else None

        constraints = self._memory_items(requirement_spec.get('constraints'))
        decisions: list[str] = []
        if plan:
            decisions.append('requirement_review approved')
        if state.get('code_files'):
            decisions.append('plan_review approved')
        if review_report:
            decisions.append('code_review approved')
        if current_status is TaskStatus.DONE:
            decisions.append('final_review approved')
        if not decisions:
            decisions.append('discovery in progress')

        preferences = self._memory_items(session.conversation_summary if session is not None else None)
        issues = self._memory_items(review_report.get('issues'))
        if not issues and test_results.get('status') == 'failed':
            issues = self._memory_items(test_results.get('summary'))
        reusable_facts = self._memory_items([
            requirement_spec.get('summary'),
            plan.get('summary'),
        ])

        lines = ['# Project Memory', '', '## Goal', f'- {project.requirement.strip() or project.title.strip()}']
        lines.extend(['', '## Constraints'])
        lines.extend(f'- {item}' for item in (constraints or ['None recorded.']))
        lines.extend(['', '## Decisions'])
        lines.extend(f'- {item}' for item in decisions)
        lines.extend(['', '## User Preferences'])
        lines.extend(f'- {item}' for item in (preferences or ['None recorded.']))
        lines.extend(['', '## Known Issues'])
        lines.extend(f'- {item}' for item in (issues or ['None recorded.']))
        lines.extend(['', '## Next Reusable Facts'])
        lines.extend(f'- {item}' for item in (reusable_facts or ['None recorded.']))

        self.manager.write_project_memory(project_id, '\n'.join(lines).rstrip() + '\n')

    @staticmethod
    def _memory_items(value: object) -> list[str]:
        items: list[str] = []
        if isinstance(value, list):
            for item in value:
                text = str(item).strip()
                if text:
                    items.append(text)
            return items
        if value is None:
            return items
        text = str(value).strip()
        if text:
            items.append(text)
        return items

    def _requirement_open_questions(self, project_id: str) -> list[str]:
        snapshot = self.graph.get_state(self._config(project_id))
        requirement_spec = snapshot.values.get('requirement_spec') or {}
        questions = requirement_spec.get('open_questions') or []
        normalized: list[str] = []
        for question in questions:
            if isinstance(question, dict):
                text = str(question.get('question') or '').strip()
            else:
                text = str(question).strip()
            if text:
                normalized.append(text)
        return normalized

    def _current_requirement_question(self, project_id: str) -> str | None:
        questions = self._requirement_open_questions(project_id)
        return questions[0] if questions else None

    def _interpret_requirement_reply(
        self,
        *,
        requirement_spec: dict[str, Any],
        current_question: str | None,
        user_reply: str,
    ) -> dict[str, object]:
        if hasattr(self.pm_agent, 'decide_requirement_turn'):
            return self.pm_agent.decide_requirement_turn(
                requirement_spec=requirement_spec,
                current_question=current_question,
                user_reply=user_reply,
            )
        if hasattr(self.pm_agent, 'interpret_requirement_reply'):
            return self.pm_agent.interpret_requirement_reply(
                requirement_spec=requirement_spec,
                current_question=current_question,
                user_reply=user_reply,
            )
        return {
            'reply': None,
            'recommendation': None,
            'requirement_update': user_reply.strip(),
            'ready_to_advance': False,
        }


    def _interpret_plan_reply(
        self,
        *,
        plan: dict[str, Any],
        user_reply: str,
    ) -> dict[str, object]:
        if hasattr(self.planner_agent, 'decide_plan_turn'):
            return self.planner_agent.decide_plan_turn(
                plan=plan,
                user_reply=user_reply,
            )
        text = user_reply.strip()
        lowered = text.lower()
        if text in {'可以', '好', '好的', '行', '确认', '同意', '批准'} or any(marker in lowered for marker in ('ok', 'yes', 'approve')):
            return {
                'reply': None,
                'recommendation': None,
                'plan_update': None,
                'ready_to_advance': True,
            }
        if any(marker in text for marker in ('建议', '你来', '你决定', '最简单')):
            return {
                'reply': None,
                'recommendation': self._stringify_plan_recommendation(plan),
                'plan_update': None,
                'ready_to_advance': False,
            }
        if any(marker in text for marker in ('修改', '调整', '改成', '换成', '增加', '减少', '不要')):
            return {
                'reply': None,
                'recommendation': None,
                'plan_update': text,
                'ready_to_advance': False,
            }
        return {
            'reply': None,
            'recommendation': None,
            'plan_update': None,
            'ready_to_advance': False,
        }

    @staticmethod
    def _stringify_plan_recommendation(plan: dict[str, Any]) -> str:
        summary = str(plan.get('summary') or '').strip()
        tasks = [str(task).strip() for task in (plan.get('tasks') or []) if str(task).strip()]
        if summary and tasks:
            return f'{summary}；先做：' + '，'.join(tasks[:2])
        if summary:
            return summary
        if tasks:
            return '建议按当前计划推进：' + '，'.join(tasks[:2])
        return '建议先按当前最小计划推进。'

    @staticmethod
    def _merge_requirement_spec_for_plan_revision(requirement_spec: dict[str, Any], plan_update: str) -> dict[str, Any]:
        updated = dict(requirement_spec)
        constraints = [str(item).strip() for item in (updated.get('constraints') or []) if str(item).strip()]
        if plan_update:
            constraints.append(f'计划调整要求：{plan_update}')
            updated['revision_request'] = plan_update
        updated['constraints'] = constraints
        return updated

    def _run_tests_with_trace(self, project_id: str, code_files: dict[str, str], *, attempt: int) -> dict[str, object]:
        with trace_span(
            name='workflow.run_tests',
            run_type='tool',
            inputs={'project_id': project_id, 'code_file_count': len(code_files), 'attempt': attempt},
            metadata={'project_id': project_id, 'attempt': attempt},
            tags=['workflow', 'testing'],
        ) as run_tree:
            result = self.sandbox.run_tests(code_files)
            run_tree.end(
                outputs={
                    'status': result.get('status'),
                    'failure_type': result.get('failure_type'),
                }
            )
            return result

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
    def _is_natural_confirmation(user_reply: str) -> bool:
        normalized = user_reply.strip().lower()
        confirmations = {
            '可以',
            '好',
            '好的',
            '行',
            '同意',
            '确认',
            '按这个来',
            '就这样',
            '没问题',
            'ok',
            'yes',
        }
        return normalized in confirmations

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
        with trace_span(
            name='workflow.create_checkpoint',
            run_type='tool',
            inputs={'project_id': project_id, 'task': task.value},
            metadata={'project_id': project_id, 'task': task.value},
            tags=['workflow', 'checkpoint'],
        ) as run_tree:
            checkpoint = None
            if task is TaskStatus.WAIT_HUMAN_REQUIREMENT:
                checkpoint = self.manager.create_checkpoint(project_id=project_id, checkpoint_type='requirement_review', available_actions=['approve', 'revise', 'reject', 'pause'])
            elif task is TaskStatus.WAIT_HUMAN_PLAN:
                checkpoint = self.manager.create_checkpoint(project_id=project_id, checkpoint_type='plan_review', available_actions=['approve', 'revise', 'reject', 'pause'])
            elif task is TaskStatus.WAIT_HUMAN_CODE:
                checkpoint = self.manager.create_checkpoint(project_id=project_id, checkpoint_type='code_review', available_actions=['approve', 'revise', 'replan', 'pause'])
            elif task is TaskStatus.WAIT_HUMAN_FINAL:
                checkpoint = self.manager.create_checkpoint(project_id=project_id, checkpoint_type='final_review', available_actions=['approve', 'revise', 'reject', 'pause'])
            run_tree.end(outputs={'checkpoint_type': checkpoint.type if checkpoint else None})
            return checkpoint

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
            return self.plan_review_reply(project_id)
        if checkpoint_type == 'code_review':
            return '开发与测试已完成，请审核代码结果。'
        if checkpoint_type == 'final_review':
            return '代码审查已完成，请进行最终审批。'
        return '项目有新的待处理阶段，请查看。'
