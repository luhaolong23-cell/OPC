from __future__ import annotations

from pydantic import BaseModel, Field

from agents.base import BaseAgent
from observability import trace_span


class CoderRunResponse(BaseModel):
    modified_files: dict[str, str] = Field(default_factory=dict)
    summary: str | None = None


class CoderAgent(BaseAgent):
    def run(self, plan: dict[str, object], current_files: dict[str, str] | None = None, task_description: str = "") -> dict[str, object]:
        with trace_span(
            name='agent.coder.run',
            run_type='chain',
            inputs={
                'plan_summary': str(plan.get('summary', '')),
                'current_file_count': len(current_files or {}),
                'task_description': task_description,
            },
            metadata={'agent_role': 'coder', 'model': self.model},
            tags=['agent', 'coder'],
        ) as run_tree:
            default_instructions = 'Implement the task and return JSON with modified_files and summary.'
            payload = {
                'plan': plan,
                'current_files': current_files or {},
                'task_description': task_description,
            }
            result = self.run_via_react(
                skill_name='coder.implement',
                default_instructions=default_instructions,
                payload=payload,
                response_format=CoderRunResponse,
                workflow_stage='coding',
                write_allowed=True,
            )
            if result is None:
                if self.llm_client is not None:
                    result = self.llm_client.generate_json(
                        instructions=self.build_instructions('coder.implement', default_instructions),
                        input_text=self.build_input_text(payload),
                    )
                else:
                    result = {
                        'modified_files': current_files or {},
                        'summary': f"implemented {plan['summary']}",
                    }
            result.setdefault('modified_files', current_files or {})
            result.setdefault('summary', f"implemented {plan['summary']}")
            run_tree.end(outputs=result)
            return result
