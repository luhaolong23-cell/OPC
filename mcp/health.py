from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MCPHealthStatus:
    healthy: bool
    error: str | None = None


class MCPHealthcheck:
    def check(self, handle: Any) -> MCPHealthStatus:
        try:
            handle.list_tools()
        except Exception as exc:  # pragma: no cover - exercised in tests
            return MCPHealthStatus(False, str(exc))
        return MCPHealthStatus(True, None)
