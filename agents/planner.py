from __future__ import annotations

from pydantic import BaseModel, Field

from agents.base import BaseAgent
from observability import trace_span


class PlannerRunResponse(BaseModel):
    summary: str | None = None
    tasks: list[str] = Field(default_factory=list)
    milestones: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


class PlannerPlanTurnResponse(BaseModel):
    reply: str | None = None
    recommendation: str | None = None
    plan_update: str | None = None
    ready_to_advance: bool = False


class PlannerAgent(BaseAgent):
    def run(self, requirement_spec: dict[str, object]) -> dict[str, object]:
        with trace_span(
            name='agent.planner.run',
            run_type='chain',
            inputs={'summary': str(requirement_spec.get('summary', ''))},
            metadata={'agent_role': 'planner', 'model': self.model},
            tags=['agent', 'planner'],
        ) as run_tree:
            default_instructions = 'Write an implementation plan and return JSON with summary, tasks, milestones, dependencies, risks, out_of_scope, and open_questions.'
            result = self.run_via_react(
                skill_name='planner.write_tasks',
                default_instructions=default_instructions,
                payload=requirement_spec,
                response_format=PlannerRunResponse,
                workflow_stage='planning',
                write_allowed=False,
            )
            if result is None:
                if self.llm_client is not None:
                    result = self.llm_client.generate_json(
                        instructions=self.build_instructions('planner.write_tasks', default_instructions),
                        input_text=self.build_input_text(requirement_spec),
                    )
                else:
                    result = {
                        'summary': str(requirement_spec['summary']),
                        'tasks': [],
                        'milestones': [],
                        'dependencies': [],
                        'risks': [],
                        'out_of_scope': [],
                        'open_questions': [],
                    }
            result.setdefault('summary', str(requirement_spec.get('summary', '')))
            result.setdefault('tasks', [])
            result.setdefault('milestones', [])
            result.setdefault('dependencies', [])
            result.setdefault('risks', [])
            result.setdefault('out_of_scope', [])
            result.setdefault('open_questions', [])
            run_tree.end(outputs=result)
            return result

    def decide_plan_turn(self, *, plan: dict[str, object], user_reply: str) -> dict[str, object]:
        with trace_span(
            name='agent.planner.decide_plan_turn',
            run_type='chain',
            inputs={'summary': str(plan.get('summary', '')), 'user_reply': user_reply},
            metadata={'agent_role': 'planner', 'model': self.model},
            tags=['agent', 'planner', 'plan_review'],
        ) as run_tree:
            payload = {
                'plan': plan,
                'user_reply': user_reply,
            }
            default_instructions = (
                'Review the current implementation plan with the user and return JSON with reply, recommendation, plan_update, and ready_to_advance. '
                'Set recommendation when the user asks you to decide, asks for a recommendation, or wants the simplest direction. '
                'Set ready_to_advance=true when the user naturally confirms the current plan. '
                'Set plan_update when the user asks to change the plan and include only the requested adjustment. '
                'Set reply when the response is ambiguous and you need a short user-facing clarification.'
            )
            result = self.run_via_react(
                skill_name='planner.write_tasks',
                default_instructions=default_instructions,
                payload=payload,
                response_format=PlannerPlanTurnResponse,
                workflow_stage='plan_review',
                write_allowed=False,
            )
            if result is None:
                if self.llm_client is not None:
                    result = self.llm_client.generate_json(
                        instructions=self.build_instructions('planner.write_tasks', default_instructions),
                        input_text=self.build_input_text(payload),
                    )
                else:
                    result = self._fallback_plan_turn(plan=plan, user_reply=user_reply)

            recommendation = _optional_text(result.get('recommendation'))
            reply = _optional_text(result.get('reply'))
            plan_update = _optional_text(result.get('plan_update'))
            ready_to_advance = bool(result.get('ready_to_advance'))

            if self._delegates_plan_tradeoff(user_reply) and not ready_to_advance:
                recommendation = recommendation or reply or self._stringify_plan_recommendation(plan)
                reply = None
                plan_update = None
            elif ready_to_advance:
                recommendation = None
                plan_update = None
            elif self._looks_like_plan_revision(user_reply):
                plan_update = plan_update or user_reply.strip()
                recommendation = None
                reply = None
            elif recommendation is None and plan_update is None and reply is None:
                reply = '如果你认可这版计划，直接确认就行；如果你想让我先建议，也可以回复“你来建议”。'

            normalized_result = {
                'reply': reply,
                'recommendation': recommendation,
                'plan_update': plan_update,
                'ready_to_advance': ready_to_advance,
            }
            run_tree.end(outputs=normalized_result)
            return normalized_result

    def _fallback_plan_turn(self, *, plan: dict[str, object], user_reply: str) -> dict[str, object]:
        text = user_reply.strip()
        if self._is_natural_confirmation(text):
            return {
                'reply': None,
                'recommendation': None,
                'plan_update': None,
                'ready_to_advance': True,
            }
        if self._delegates_plan_tradeoff(text):
            return {
                'reply': None,
                'recommendation': self._stringify_plan_recommendation(plan),
                'plan_update': None,
                'ready_to_advance': False,
            }
        if self._looks_like_plan_revision(text):
            return {
                'reply': None,
                'recommendation': None,
                'plan_update': text,
                'ready_to_advance': False,
            }
        return {
            'reply': '如果你认可这版计划，直接确认就行；如果你想让我先建议，也可以回复“你来建议”。',
            'recommendation': None,
            'plan_update': None,
            'ready_to_advance': False,
        }

    @staticmethod
    def _delegates_plan_tradeoff(user_reply: str) -> bool:
        normalized = user_reply.strip().lower()
        markers = ('建议', '你来', '你决定', '最简单', 'you decide', 'you suggest', 'no preference')
        return any(marker in normalized for marker in markers)

    @staticmethod
    def _looks_like_plan_revision(user_reply: str) -> bool:
        normalized = user_reply.strip()
        markers = ('修改', '调整', '改成', '换成', '增加', '减少', '不要')
        return any(marker in normalized for marker in markers)

    @staticmethod
    def _is_natural_confirmation(user_reply: str) -> bool:
        normalized = user_reply.strip().lower()
        if not normalized:
            return False
        exact_matches = {
            '可以', '好', '好的', '行', '确认', '同意', '批准', '按这个来', '就这样',
            'ok', 'okay', 'yes', 'approve', 'approved',
        }
        if normalized in exact_matches:
            return True
        markers = ('可以', '同意', '确认', '按这个', '就这样', '没问题', 'go ahead')
        return any(marker in normalized for marker in markers)

    @staticmethod
    def _stringify_plan_recommendation(plan: dict[str, object]) -> str:
        summary = str(plan.get('summary') or '').strip()
        tasks = [str(task).strip() for task in (plan.get('tasks') or []) if str(task).strip()]
        if summary and tasks:
            return f'{summary}；先做：' + '，'.join(tasks[:2])
        if summary:
            return summary
        if tasks:
            return '建议按当前计划推进：' + '，'.join(tasks[:2])
        return '建议先按当前最小计划推进。'


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
