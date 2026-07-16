from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel

from agents.base import BaseAgent
from observability import trace_span
from workspace.state import WechatSessionRecord


class DirectorSystemCommand(str, Enum):
    RESET_SESSION = 'reset_session'
    LIST_PROJECTS = 'list_projects'
    SWITCH_PROJECT = 'switch_project'
    DELETE_PROJECT = 'delete_project'
    STATUS = 'status'


class DirectorStatePatch(BaseModel):
    requirement_draft: str | None = None
    conversation_summary: str | None = None
    ready_to_start: bool = False


class DirectorRunResponse(BaseModel):
    reply: str
    state_patch: DirectorStatePatch | None = None


@dataclass(slots=True, frozen=True)
class DirectorTurn:
    message: str
    requirement_draft: str | None = None
    conversation_summary: str | None = None
    ready_to_start: bool = False
    system_command: DirectorSystemCommand | None = None
    target: str | None = None


DEFAULT_CHAT_REPLY = '我先继续和你澄清需求，不会自动进入开发流程。'


class DirectorAgent(BaseAgent):
    def run(
        self,
        message: str,
        session: WechatSessionRecord | None = None,
        project_memory: str | None = None,
        project_context: dict[str, Any] | None = None,
    ) -> DirectorTurn:
        with trace_span(
            name='agent.director.run',
            run_type='chain',
            inputs={
                'message': message,
                'session_mode': session.mode.value if session is not None else None,
                'active_project_id': session.active_project_id if session is not None else None,
                'project_context': project_context,
            },
            metadata={'agent_role': 'director', 'model': self.model},
            tags=['agent', 'director'],
        ) as run_tree:
            payload = {
                'message': message,
                'project_memory': project_memory,
                'session': {
                    'mode': session.mode.value if session is not None else None,
                    'active_project_id': session.active_project_id if session is not None else None,
                    'conversation_summary': session.conversation_summary if session is not None else None,
                    'last_requirement_draft': session.last_requirement_draft if session is not None else None,
                },
                'project_context': project_context,
            }
            default_instructions = (
                'You are the main user-facing conversation agent for a software development assistant. '
                'Hold a natural conversation with the user, refine the idea, use tools when they add evidence, and decide whether the current requirement is actionable enough to open a minimal project. '
                'Return JSON with keys: reply and state_patch. '
                'state_patch may contain requirement_draft, conversation_summary, and ready_to_start. '
                'Keep state_patch.ready_to_start=false until the requirement is concrete enough for a smallest useful implementation. '
                'When the user delegates decisions to you, prefer making the smallest reasonable default product choice instead of bouncing the question back. '
                'Do not emit workflow actions or hidden reasoning; only return the conversational reply and the minimal state patch needed by the system.'
            )
            result = self.run_via_react(
                skill_name='director.converse',
                default_instructions=default_instructions,
                payload=payload,
                response_format=DirectorRunResponse,
                workflow_stage='conversation',
                write_allowed=False,
            )
            if result is None:
                if self.llm_client is not None:
                    result = self.llm_client.generate_json(
                        instructions=self.build_instructions('director.converse', default_instructions),
                        input_text=self.build_input_text(payload),
                    )
                else:
                    result = {
                        'reply': DEFAULT_CHAT_REPLY,
                        'state_patch': {
                            'requirement_draft': None,
                            'conversation_summary': None,
                            'ready_to_start': False,
                        },
                    }
            state_patch = _coerce_state_patch(result)
            turn = DirectorTurn(
                message=str(result.get('reply') or DEFAULT_CHAT_REPLY).strip() or DEFAULT_CHAT_REPLY,
                requirement_draft=_optional_text(state_patch.get('requirement_draft')),
                conversation_summary=_optional_text(state_patch.get('conversation_summary')),
                ready_to_start=bool(state_patch.get('ready_to_start')),
            )
            run_tree.end(
                outputs={
                    'message': turn.message,
                    'requirement_draft': turn.requirement_draft,
                    'conversation_summary': turn.conversation_summary,
                    'ready_to_start': turn.ready_to_start,
                }
            )
            return turn


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None



def _coerce_state_patch(result: dict[str, Any]) -> dict[str, object]:
    state_patch = result.get('state_patch')
    if isinstance(state_patch, dict):
        return dict(state_patch)
    # Backward-compatible fallback while prompts and cached outputs converge.
    return {
        'requirement_draft': result.get('requirement_draft'),
        'conversation_summary': result.get('conversation_summary'),
        'ready_to_start': result.get('ready_to_start', False),
    }
