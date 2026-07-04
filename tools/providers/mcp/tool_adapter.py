from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tools.specs import ToolCallRequest, ToolCallResult


@dataclass
class MCPToolAdapter:
    server_name: str
    remote_tool: str
    handle: Any

    def execute(self, request: ToolCallRequest) -> ToolCallResult:
        raw_result = self.handle.call_tool(self.remote_tool, request.arguments)
        if isinstance(raw_result, ToolCallResult):
            return raw_result
        return ToolCallResult(
            ok=raw_result["ok"],
            output=raw_result.get("output"),
            error=raw_result.get("error"),
            provider=raw_result.get("provider", self.server_name),
            latency_ms=raw_result.get("latency_ms", 0),
            metadata=raw_result.get("metadata", {}),
        )
