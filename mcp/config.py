from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MCPServerConfig:
    name: str
    transport: str
    command: list[str] | None
    url: str | None
    env: dict[str, str]
    enabled: bool
    timeout_seconds: float
    tags: tuple[str, ...] = ()


def load_mcp_servers_file(path: str | Path) -> tuple[MCPServerConfig, ...]:
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = Path.cwd() / file_path
    payload = json.loads(file_path.read_text())
    return tuple(
        MCPServerConfig(
            name=item["name"],
            transport=item["transport"],
            command=item.get("command"),
            url=item.get("url"),
            env=item.get("env", {}),
            enabled=item.get("enabled", True),
            timeout_seconds=item.get("timeout_seconds", 5.0),
            tags=tuple(item.get("tags", ())),
        )
        for item in payload.get("servers", [])
    )
