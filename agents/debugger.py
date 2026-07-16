from __future__ import annotations

from pydantic import BaseModel, Field

from agents.base import BaseAgent
from observability import trace_span


class DebuggerRunResponse(BaseModel):
    patches: dict[str, str] = Field(default_factory=dict)
    diagnosis: str | None = None


class DebuggerAgent(BaseAgent):
    def run(self, code_files: dict[str, str], test_results: dict[str, object], error_log: str | None = None) -> dict[str, object]:
        with trace_span(
            name='agent.debugger.run',
            run_type='chain',
            inputs={
                'code_file_count': len(code_files),
                'test_status': test_results.get('status'),
                'failure_type': test_results.get('failure_type'),
            },
            metadata={'agent_role': 'debugger', 'model': self.model},
            tags=['agent', 'debugger'],
        ) as run_tree:
            default_instructions = 'Debug the failure and return JSON with patches and diagnosis.'
            payload = {
                'code_files': code_files,
                'test_results': test_results,
                'error_log': error_log,
            }
            result = self.run_via_react(
                skill_name='debugger.fix',
                default_instructions=default_instructions,
                payload=payload,
                response_format=DebuggerRunResponse,
                workflow_stage='debugging',
                write_allowed=True,
            )
            if result is None:
                if self.llm_client is not None:
                    result = self.llm_client.generate_json(
                        instructions=self.build_instructions('debugger.fix', default_instructions),
                        input_text=self.build_input_text(payload),
                    )
                else:
                    result = {
                        'patches': code_files,
                        'diagnosis': error_log or test_results.get('summary', ''),
                    }
            result.setdefault('patches', code_files)
            result.setdefault('diagnosis', error_log or test_results.get('summary', ''))
            run_tree.end(outputs=result)
            return result
