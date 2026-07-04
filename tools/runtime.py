from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from tools.specs import ToolCallRequest, ToolCallResult


class ToolExecutor(Protocol):
    def execute(self, request: ToolCallRequest) -> ToolCallResult: ...


@dataclass
class BackendToolExecutor:
    backend: Any

    def execute(self, request: ToolCallRequest) -> ToolCallResult:
        raw_result = self.backend.execute(request)
        if isinstance(raw_result, ToolCallResult):
            return raw_result
        return ToolCallResult(
            ok=raw_result["ok"],
            output=raw_result.get("output"),
            error=raw_result.get("error"),
            provider=raw_result.get("provider", "local"),
            latency_ms=raw_result.get("latency_ms", 0),
            metadata=raw_result.get("metadata", {}),
        )
