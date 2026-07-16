from __future__ import annotations

from pydantic import BaseModel, Field

from agents.base import BaseAgent
from observability import trace_span


class ReviewerRunResponse(BaseModel):
    approved: bool = True
    issues: list[str] = Field(default_factory=list)
    risk_level: str = 'low'
    summary: str | None = None


class ReviewerAgent(BaseAgent):
    def run(self, plan: dict[str, object], code_files: dict[str, str], test_results: dict[str, object]) -> dict[str, object]:
        with trace_span(
            name='agent.reviewer.run',
            run_type='chain',
            inputs={
                'plan_summary': str(plan.get('summary', '')),
                'code_file_count': len(code_files),
                'test_status': test_results.get('status'),
            },
            metadata={'agent_role': 'reviewer', 'model': self.model},
            tags=['agent', 'reviewer'],
        ) as run_tree:
            default_instructions = 'Review the change and return JSON with approved, issues, risk_level, and summary.'
            payload = {
                'plan': plan,
                'code_files': code_files,
                'test_results': test_results,
            }
            result = self.run_via_react(
                skill_name='reviewer.code_review',
                default_instructions=default_instructions,
                payload=payload,
                response_format=ReviewerRunResponse,
                workflow_stage='review',
                write_allowed=False,
            )
            if result is None:
                if self.llm_client is not None:
                    result = self.llm_client.generate_json(
                        instructions=self.build_instructions('reviewer.code_review', default_instructions),
                        input_text=self.build_input_text(payload),
                    )
                else:
                    result = {
                        'approved': True,
                        'issues': [],
                        'risk_level': 'low',
                        'summary': f"reviewed {plan['summary']}",
                    }
            result.setdefault('approved', True)
            result.setdefault('issues', [])
            result.setdefault('risk_level', 'low')
            result.setdefault('summary', f"reviewed {plan['summary']}")
            run_tree.end(outputs=result)
            return result
