from __future__ import annotations

from scripts.launch_stack import build_commands


def test_build_commands_returns_main_and_bridge_launch_commands() -> None:
    commands = build_commands(main_host='0.0.0.0', main_port=8000, bridge_host='0.0.0.0', bridge_port=9001)

    assert commands['main'] == ['python3', '-m', 'uvicorn', 'main:create_app', '--factory', '--host', '0.0.0.0', '--port', '8000']
    assert commands['bridge'] == ['python3', '-m', 'wecom_bot_bridge', '--host', '0.0.0.0', '--port', '9001']
