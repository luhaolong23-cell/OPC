from __future__ import annotations

from pydantic import BaseModel, Field

from agents.base import BaseAgent
from observability import trace_span


class PMRecommendedDirection(BaseModel):
    choice: str
    justification: str | None = None


class PMRunResponse(BaseModel):
    summary: str | None = None
    candidate_solutions: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    recommended_direction: PMRecommendedDirection | None = None
    next_action: str | None = None


class PMRequirementTurnResponse(BaseModel):
    reply: str | None = None
    recommendation: str | None = None
    requirement_update: str | None = None
    ready_to_advance: bool = False


class PMAgent(BaseAgent):
    def run(self, requirement: str, conversation: list[dict] | None = None) -> dict[str, object]:
        with trace_span(
            name='agent.pm.run',
            run_type='chain',
            inputs={'requirement': requirement, 'conversation_length': len(conversation or [])},
            metadata={'agent_role': 'pm', 'model': self.model},
            tags=['agent', 'pm'],
        ) as run_tree:
            default_instructions = 'Brainstorm the requirement and return JSON with summary, candidate_solutions, open_questions, assumptions, risks, constraints, recommended_direction, and next_action. Allowed next_action values are ask_question or close_brainstorm. If open_questions is non-empty, set next_action=ask_question and make the first question the single highest-leverage Socratic question to ask next. If open_questions is empty, set next_action=close_brainstorm. Do not mix asking a new question with closing the brainstorm in the same turn.'
            payload = {'requirement': requirement, 'conversation': conversation or []}
            result = self.run_via_react(
                skill_name='pm.brainstorm',
                default_instructions=default_instructions,
                payload=payload,
                response_format=PMRunResponse,
                workflow_stage='discovery',
                write_allowed=False,
            )
            if result is None:
                if self.llm_client is not None:
                    result = self.llm_client.generate_json(
                        instructions=self.build_instructions('pm.brainstorm', default_instructions),
                        input_text=self.build_input_text(payload),
                    )
                else:
                    result = {
                        'summary': requirement,
                        'candidate_solutions': [],
                        'open_questions': [],
                        'assumptions': [],
                        'risks': [],
                        'constraints': [],
                        'recommended_direction': None,
                    }
            result.setdefault('summary', requirement)
            result.setdefault('candidate_solutions', [])
            result.setdefault('open_questions', [])
            result.setdefault('assumptions', [])
            result.setdefault('risks', [])
            result.setdefault('constraints', [])
            result.setdefault('recommended_direction', None)
            result.setdefault('next_action', 'ask_question' if result.get('open_questions') else 'close_brainstorm')
            run_tree.end(outputs=result)
            return result

    def interpret_requirement_reply(
        self,
        *,
        requirement_spec: dict[str, object],
        current_question: str | None,
        user_reply: str,
    ) -> dict[str, object]:
        return self.decide_requirement_turn(
            requirement_spec=requirement_spec,
            current_question=current_question,
            user_reply=user_reply,
        )

    def decide_requirement_turn(
        self,
        *,
        requirement_spec: dict[str, object],
        current_question: str | None,
        user_reply: str,
    ) -> dict[str, object]:
        with trace_span(
            name='agent.pm.decide_requirement_turn',
            run_type='chain',
            inputs={
                'has_current_question': bool(current_question),
                'user_reply': user_reply,
            },
            metadata={'agent_role': 'pm', 'model': self.model},
            tags=['agent', 'pm', 'requirement-turn'],
        ) as run_tree:
            normalized = user_reply.strip()
            default_instructions = (
                'You are the PM handling the next requirement-discussion turn in a software delivery workflow. '
                'Return JSON with keys: reply, recommendation, requirement_update, ready_to_advance. '
                'Set recommendation when the user explicitly delegates a product or scope tradeoff to you, such as saying you decide, you suggest, no preference, or whatever is simplest. '
                'Set ready_to_advance=true only when the user clearly confirms the current requirement scope or accepts the current recommendation and wants to move on. '
                'Set requirement_update when the user adds concrete requirement details, constraints, or preferences that should be merged into the requirement. '
                'Set reply when you need a short user-facing clarification or correction because the reply is vague, contradictory, off-topic, or asks about a later workflow stage instead of answering the current question. '
                'Always ground the decision in current_question when one exists. '
                'Do not copy delegation phrases like you decide or you suggest into requirement_update. '
                'Do not copy meta workflow questions such as asking for the plan, progress, or next step into requirement_update. '
                'Do not invent extra technologies, libraries, or product scope inside requirement_update beyond what the user actually said. '
                'Only one of recommendation, requirement_update, or reply should normally be populated in the same turn.'
            )
            payload = {
                'requirement_spec': requirement_spec,
                'current_question': current_question,
                'user_reply': normalized,
            }
            result = self.run_via_react(
                skill_name='pm.brainstorm',
                default_instructions=default_instructions,
                payload=payload,
                response_format=PMRequirementTurnResponse,
                workflow_stage='discovery',
                write_allowed=False,
            )
            if result is None:
                if self.llm_client is not None:
                    result = self.llm_client.generate_json(
                        instructions=self.build_instructions('pm.brainstorm', default_instructions),
                        input_text=self.build_input_text(payload),
                    )
                else:
                    result = self._fallback_requirement_turn(
                        requirement_spec=requirement_spec,
                        current_question=current_question,
                        user_reply=normalized,
                    )

            recommendation = _optional_text(result.get('recommendation'))
            reply = _optional_text(result.get('reply'))
            requirement_update = _optional_text(result.get('requirement_update'))
            ready_to_advance = bool(result.get('ready_to_advance'))

            if self._delegates_requirement_tradeoff(normalized) and not ready_to_advance:
                recommendation = recommendation or reply
                if not recommendation or self._is_weak_requirement_recommendation(reply=recommendation, current_question=current_question):
                    recommendation = self._fallback_requirement_recommendation(
                        requirement_spec=requirement_spec,
                        current_question=current_question,
                    )
                reply = None
                requirement_update = None
            elif current_question and self._looks_like_requirement_meta_reply(
                user_reply=normalized,
                requirement_update=requirement_update,
            ):
                reply = self._requirement_meta_reply(current_question)
                recommendation = None
                requirement_update = None
                ready_to_advance = False
            elif ready_to_advance:
                recommendation = None
                requirement_update = None
            elif requirement_update is None and recommendation is None and reply is None:
                requirement_update = normalized or None

            normalized_result = {
                'reply': reply,
                'recommendation': recommendation,
                'requirement_update': requirement_update,
                'ready_to_advance': ready_to_advance,
            }
            run_tree.end(outputs=normalized_result)
            return normalized_result

    def _fallback_requirement_turn(
        self,
        *,
        requirement_spec: dict[str, object],
        current_question: str | None,
        user_reply: str,
    ) -> dict[str, object]:
        if self._delegates_requirement_tradeoff(user_reply):
            return {
                'reply': None,
                'recommendation': self._fallback_requirement_recommendation(
                    requirement_spec=requirement_spec,
                    current_question=current_question,
                ),
                'requirement_update': None,
                'ready_to_advance': False,
            }
        if current_question and self._looks_like_requirement_meta_reply(
            user_reply=user_reply,
            requirement_update=user_reply,
        ):
            return {
                'reply': self._requirement_meta_reply(current_question),
                'recommendation': None,
                'requirement_update': None,
                'ready_to_advance': False,
            }
        if self._is_natural_confirmation(user_reply):
            return {
                'reply': None,
                'recommendation': None,
                'requirement_update': None,
                'ready_to_advance': True,
            }
        return {
            'reply': None,
            'recommendation': None,
            'requirement_update': user_reply,
            'ready_to_advance': False,
        }

    @staticmethod
    def _delegates_requirement_tradeoff(user_reply: str) -> bool:
        normalized = user_reply.strip().lower()
        markers = (
            '你来建议',
            '你决定',
            '你来定',
            '没想法',
            '都行',
            'whatever is simplest',
            'you decide',
            'you suggest',
            'no preference',
        )
        return any(marker in normalized for marker in markers)

    @staticmethod
    def _looks_like_requirement_meta_reply(*, user_reply: str, requirement_update: object | None) -> bool:
        candidate = str(requirement_update or user_reply).strip().lower()
        if not candidate or len(candidate) > 24:
            return False
        markers = ('计划', '规划', '方案', '进度', '下一步', '下一阶段', 'plan', 'progress', 'next step')
        prefixes = ('计划', '给我', '先给', '看看', '说说', '那')
        suffixes = ('呢', '吗', '么', '?', '？')
        return any(marker in candidate for marker in markers) and (
            candidate.startswith(prefixes) or candidate.endswith(suffixes)
        )

    @staticmethod
    def _requirement_meta_reply(current_question: str) -> str:
        return f'还没到规划阶段，我还需要先确认这条信息：{current_question}。如果你暂时没想法，也可以回复“你来建议”。'

    @staticmethod
    def _default_answer_for_current_question(current_question: str | None) -> str:
        if not current_question:
            return ''
        question = current_question.strip()
        if '目标用户' in question or '用户群' in question:
            return '默认面向普通单人玩家，先按个人娱乐型小游戏设计，不额外细分目标人群。'
        if '平台' in question:
            return '默认先做桌面端，优先保证本地能直接运行。'
        if '语言' in question:
            return '默认用 Python，实现成本最低，便于先做出最小可运行版本。'
        if '图形界面' in question or '图形库' in question:
            return '默认先做 Python CLI 最小版，不加图形界面，先保证核心玩法可运行。'
        if ('目标' in question and '功能' in question) or '预期功能' in question:
            return '默认先做一个最小可交付版本，只保留一个核心功能闭环，其他扩展功能后置。'
        return ''

    @staticmethod
    def _is_weak_requirement_recommendation(*, reply: str, current_question: str | None) -> bool:
        normalized_reply = reply.strip().lower()
        if not normalized_reply:
            return True
        weak_markers = ('先明确', '先确认', '先识别', '先了解', '需要先', '还需要', '需要知道', 'ask', 'clarify')
        procedural_markers = (
            '访谈', '问卷', '调研', '头脑风暴', '收集反馈', '了解需求', 'stakeholder', 'survey', 'research',
            '请提供更多信息', '需要明确以下几点', '为了更好地建议', '为了更好地', '我们需要明确',
        )
        if any(marker in normalized_reply for marker in procedural_markers):
            return True
        if '1.' in normalized_reply and ('2.' in normalized_reply or '3.' in normalized_reply):
            return True
        if current_question and '目标用户' in current_question and '目标用户' in normalized_reply:
            return any(marker in normalized_reply for marker in weak_markers)
        return normalized_reply.endswith('?') or normalized_reply.endswith('？')

    @staticmethod
    def _fallback_requirement_recommendation(*, requirement_spec: dict[str, object], current_question: str | None) -> str:
        suggestion = PMAgent._default_answer_for_current_question(current_question)
        direction = requirement_spec.get('recommended_direction')
        if not suggestion and isinstance(direction, dict):
            choice = str(direction.get('choice') or '').strip()
            justification = str(direction.get('justification') or '').strip()
            if choice and justification:
                suggestion = f'{choice}；理由：{justification}'
            else:
                suggestion = choice or justification
        if not suggestion:
            candidates = [str(item).strip() for item in (requirement_spec.get('candidate_solutions') or []) if str(item).strip()]
            if candidates:
                suggestion = candidates[0]
        if not suggestion:
            suggestion = '按最简单可交付的方案推进。'
        if current_question:
            return f'针对当前问题「{current_question}」，我的建议是：{suggestion}'
        return f'我的建议是：{suggestion}'

    @staticmethod
    def _is_natural_confirmation(user_reply: str) -> bool:
        normalized = user_reply.strip().lower()
        if not normalized:
            return False
        exact_matches = {
            '可以', '好', '好的', '行', '没问题', '确认', '同意', '按这个来', '就这样', '开始吧',
            'ok', 'okay', 'yes', 'approved', 'approve',
        }
        if normalized in exact_matches:
            return True
        confirmation_markers = ('可以', '同意', '确认', '按这个', '就这样', '没问题', 'go ahead')
        return any(marker in normalized for marker in confirmation_markers)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
