from __future__ import annotations

from tests.factories.app import build_test_settings


def test_build_test_settings_uses_tmp_workspace_and_allows_overrides(tmp_path) -> None:
    settings = build_test_settings(
        tmp_path,
        llm_model="gpt-custom",
        opc_internal_token="opc-token",
    )

    assert settings.app_name == "OPC Development"
    assert settings.database_url == f"sqlite:///{tmp_path / 'opc.db'}"
    assert settings.workspace_root == tmp_path / "projects"
    assert settings.llm_model == "gpt-custom"
    assert settings.opc_internal_token == "opc-token"
