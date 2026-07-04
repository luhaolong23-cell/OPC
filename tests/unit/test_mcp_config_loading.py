from __future__ import annotations

from mcp.config import load_mcp_servers_file


def test_load_mcp_servers_file_reads_server_configs() -> None:
    servers = load_mcp_servers_file("tests/contracts/samples/mcp_servers_config.json")

    assert len(servers) == 1
    assert servers[0].name == "context7"
    assert servers[0].transport == "stdio"
    assert servers[0].tags == ("docs",)
