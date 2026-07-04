from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.runtime.execution_context import ExecutionContext


@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    description: str
    capability_tags: tuple[str, ...]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    side_effect_level: str
    provider: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCallRequest:
    tool_name: str
    arguments: dict[str, Any]
    context: ExecutionContext


@dataclass(frozen=True)
class ToolCallResult:
    ok: bool
    output: dict[str, Any] | None
    error: str | None
    provider: str
    latency_ms: int
    metadata: dict[str, Any] = field(default_factory=dict)
