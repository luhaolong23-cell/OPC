from __future__ import annotations

from wecom_bot_bridge.__main__ import build_uvicorn_kwargs


def test_build_uvicorn_kwargs_uses_bridge_settings_values() -> None:
    kwargs = build_uvicorn_kwargs(host='0.0.0.0', port=9100, log_level='debug')

    assert kwargs['app'] == 'wecom_bot_bridge.app:create_app'
    assert kwargs['factory'] is True
    assert kwargs['host'] == '0.0.0.0'
    assert kwargs['port'] == 9100
    assert kwargs['log_level'] == 'debug'
