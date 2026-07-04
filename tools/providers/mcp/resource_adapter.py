from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tools.specs import ToolCallRequest, ToolCallResult


@dataclass
class MCPResourceAdapter:
    server_name: str
    resource_uri: str
    handle: Any

    def execute(self, request: ToolCallRequest) -> ToolCallResult:
        content = self.handle.read_resource(self.resource_uri)
        return ToolCallResult(
            ok=True,
            output={"content": content},
            error=None,
            provider=self.server_name,
            latency_ms=0,
        )
