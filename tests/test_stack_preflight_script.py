from __future__ import annotations

from scripts.preflight_stack import collect_missing_env_vars


def test_collect_missing_env_vars_reports_missing_bridge_credentials() -> None:
    env = {
        'OPC_INTERNAL_TOKEN': 'opc-token',
        'WECOM_BRIDGE_NOTIFY_TOKEN': 'bridge-token',
        'OPC_BASE_URL': 'http://127.0.0.1:8000',
    }

    missing = collect_missing_env_vars(env)

    assert 'WECOM_BOT_ID' in missing
    assert 'WECOM_BOT_SECRET' in missing


def test_collect_missing_env_vars_returns_empty_when_required_values_exist() -> None:
    env = {
        'OPC_INTERNAL_TOKEN': 'opc-token',
        'WECOM_BRIDGE_NOTIFY_TOKEN': 'bridge-token',
        'WECOM_BOT_ID': 'bot-id',
        'WECOM_BOT_SECRET': 'bot-secret',
        'OPC_BASE_URL': 'http://127.0.0.1:8000',
    }

    missing = collect_missing_env_vars(env)

    assert missing == []


def test_collect_missing_env_vars_treats_placeholder_values_as_missing() -> None:
    env = {
        'OPC_INTERNAL_TOKEN': 'replace-with-opc-internal-token',
        'WECOM_BRIDGE_NOTIFY_TOKEN': 'replace-with-bridge-notify-token',
        'WECOM_BOT_ID': 'replace-with-wecom-bot-id',
        'WECOM_BOT_SECRET': 'replace-with-wecom-bot-secret',
        'OPC_BASE_URL': 'http://127.0.0.1:8000',
    }

    missing = collect_missing_env_vars(env)

    assert 'OPC_INTERNAL_TOKEN' in missing
    assert 'WECOM_BRIDGE_NOTIFY_TOKEN' in missing
    assert 'WECOM_BOT_ID' in missing
    assert 'WECOM_BOT_SECRET' in missing
