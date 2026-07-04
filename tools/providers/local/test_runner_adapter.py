from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tools.specs import ToolCallRequest, ToolCallResult


@dataclass
class SandboxTestRunnerAdapter:
    sandbox: Any

    def execute(self, request: ToolCallRequest) -> ToolCallResult:
        result = self.sandbox.run_tests(request.arguments.get("code_files", {}))
        return ToolCallResult(
            ok=True,
            output=result,
            error=None,
            provider="local",
            latency_ms=0,
        )
