from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Any, Protocol

from mcp.config import MCPServerConfig


class MCPTransportClient(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def list_tools(self) -> list[Any]: ...
    def list_resources(self) -> list[Any]: ...
    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...
    def read_resource(self, uri: str) -> str: ...


@dataclass
class UnavailableMCPTransportClient:
    error: str

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def list_tools(self) -> list[Any]:
        raise RuntimeError(self.error)

    def list_resources(self) -> list[Any]:
        raise RuntimeError(self.error)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError(self.error)

    def read_resource(self, uri: str) -> str:
        raise RuntimeError(self.error)


@dataclass
class StdioMCPTransportClient:
    config: MCPServerConfig
    process: subprocess.Popen[str] | None = None

    def start(self) -> None:
        if self.process is not None:
            return
        if not self.config.command:
            raise RuntimeError(f"stdio MCP server {self.config.name} requires a command")
        env = os.environ.copy()
        env.update(self.config.env)
        self.process = subprocess.Popen(
            self.config.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

    def stop(self) -> None:
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=self.config.timeout_seconds)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=self.config.timeout_seconds)
        finally:
            self.process = None

    def _unavailable(self) -> RuntimeError:
        return RuntimeError(f"MCP stdio transport for server {self.config.name} is not connected to a protocol bridge")

    def list_tools(self) -> list[Any]:
        raise self._unavailable()

    def list_resources(self) -> list[Any]:
        raise self._unavailable()

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        raise self._unavailable()

    def read_resource(self, uri: str) -> str:
        raise self._unavailable()


@dataclass
class HttpMCPTransportClient:
    config: MCPServerConfig

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def _unavailable(self) -> RuntimeError:
        return RuntimeError(f"MCP http transport for server {self.config.name} is not connected to a protocol bridge")

    def list_tools(self) -> list[Any]:
        raise self._unavailable()

    def list_resources(self) -> list[Any]:
        raise self._unavailable()

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        raise self._unavailable()

    def read_resource(self, uri: str) -> str:
        raise self._unavailable()


@dataclass
class MCPServerHandle:
    config: MCPServerConfig
    client: MCPTransportClient

    def start(self) -> None:
        self.client.start()

    def stop(self) -> None:
        self.client.stop()

    def list_tools(self) -> list[Any]:
        return self.client.list_tools()

    def list_resources(self) -> list[Any]:
        return self.client.list_resources()

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.client.call_tool(name, arguments)

    def read_resource(self, uri: str) -> str:
        return self.client.read_resource(uri)


def build_mcp_server_handle(
    config: MCPServerConfig,
    *,
    stdio_client_factory=None,
    http_client_factory=None,
) -> MCPServerHandle:
    if not config.enabled:
        return MCPServerHandle(
            config=config,
            client=UnavailableMCPTransportClient(
                error=f"MCP server {config.name} is disabled",
            ),
        )
    if config.transport == "stdio":
        client = stdio_client_factory(config) if stdio_client_factory is not None else StdioMCPTransportClient(config)
        return MCPServerHandle(config=config, client=client)
    if config.transport == "http":
        client = http_client_factory(config) if http_client_factory is not None else HttpMCPTransportClient(config)
        return MCPServerHandle(config=config, client=client)
    return MCPServerHandle(
        config=config,
        client=UnavailableMCPTransportClient(
            error=f"unsupported MCP transport {config.transport} for server {config.name}",
        ),
    )
