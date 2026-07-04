from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LogicalToolProviderMapping:
    server: str
    remote_tool: str
    priority: int


@dataclass(frozen=True)
class LogicalToolMapping:
    logical_tool: str
    providers: tuple[LogicalToolProviderMapping, ...]


class LogicalToolMappingRegistry:
    def __init__(self, mappings: dict[str, LogicalToolMapping]) -> None:
        self._mappings = mappings

    @classmethod
    def from_file(cls, path: str | Path) -> "LogicalToolMappingRegistry":
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = Path.cwd() / file_path
        payload = json.loads(file_path.read_text())
        mappings: dict[str, LogicalToolMapping] = {}
        for item in payload["mappings"]:
            providers = tuple(
                sorted(
                    (
                        LogicalToolProviderMapping(
                            server=provider["server"],
                            remote_tool=provider["remote_tool"],
                            priority=provider["priority"],
                        )
                        for provider in item["providers"]
                    ),
                    key=lambda provider: provider.priority,
                    reverse=True,
                )
            )
            mapping = LogicalToolMapping(
                logical_tool=item["logical_tool"],
                providers=providers,
            )
            mappings[mapping.logical_tool] = mapping
        return cls(mappings)

    def get(self, logical_tool: str) -> LogicalToolMapping:
        return self._mappings[logical_tool]
