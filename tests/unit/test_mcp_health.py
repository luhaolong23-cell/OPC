from __future__ import annotations

from mcp.health import MCPHealthcheck


class HealthyHandle:
    def list_tools(self) -> list[dict]:
        return []


class BrokenHandle:
    def list_tools(self) -> list[dict]:
        raise RuntimeError("boom")


def test_mcp_healthcheck_marks_handle_healthy_when_list_tools_succeeds() -> None:
    result = MCPHealthcheck().check(HealthyHandle())

    assert result.healthy is True
    assert result.error is None


def test_mcp_healthcheck_marks_handle_unhealthy_when_list_tools_raises() -> None:
    result = MCPHealthcheck().check(BrokenHandle())

    assert result.healthy is False
    assert result.error == "boom"
