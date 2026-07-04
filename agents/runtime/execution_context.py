from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionContext:
    agent_name: str
    workflow_stage: str
    project_type: str | None
    environment: str
    user_mode: str
    network_allowed: bool
    write_allowed: bool
    external_allowed: bool
