from __future__ import annotations

from dataclasses import dataclass

from agents.runtime.execution_context import ExecutionContext
from tools.defaults import build_default_tool_registry
from tools.specs import ToolCallRequest


@dataclass
class FakeSandbox:
    def run_tests(self, code_files: dict[str, str]) -> dict[str, object]:
        return {
            "status": "passed",
            "failure_type": None,
            "summary": f"ran {sorted(code_files)}",
            "raw_logs": "",
        }


def test_default_test_runner_executes_through_local_adapter() -> None:
    registry = build_default_tool_registry(sandbox=FakeSandbox())

    result = registry.execute(
        ToolCallRequest(
            tool_name="test_runner",
            arguments={"code_files": {"app.py": "print('ok')"}},
            context=ExecutionContext(
                agent_name="coder",
                workflow_stage="coding",
                project_type="python",
                environment="local",
                user_mode="interactive",
                network_allowed=False,
                write_allowed=True,
                external_allowed=False,
            ),
        )
    )

    assert result.ok is True
    assert result.output == {
        "status": "passed",
        "failure_type": None,
        "summary": "ran ['app.py']",
        "raw_logs": "",
    }
