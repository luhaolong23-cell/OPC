from __future__ import annotations

from mcp.mapping import LogicalToolMapping, LogicalToolProviderMapping


def choose_available_provider(
    mapping: LogicalToolMapping,
    available_servers: set[str],
) -> LogicalToolProviderMapping | None:
    for provider in mapping.providers:
        if provider.server in available_servers:
            return provider
    return None
