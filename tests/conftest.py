from __future__ import annotations

from pathlib import Path

import pytest

from tests.factories.app import build_main_test_client, build_test_settings, create_workspace_manager


_PATH_MARKERS = {
    "unit": "unit",
    "component": "component",
    "api": "api",
    "integration": "integration",
    "scenario": "scenario",
    "contracts": "contract",
    "live": "live",
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        path_parts = Path(str(item.fspath)).parts
        for path_name, marker_name in _PATH_MARKERS.items():
            if path_name in path_parts:
                item.add_marker(marker_name)


@pytest.fixture
def settings_factory(tmp_path):
    def factory(**overrides):
        return build_test_settings(tmp_path, **overrides)

    return factory


@pytest.fixture
def workspace_manager_factory(tmp_path):
    def factory(**overrides):
        return create_workspace_manager(tmp_path, **overrides)

    return factory


@pytest.fixture
def main_client_factory(tmp_path):
    def factory(**app_kwargs):
        return build_main_test_client(tmp_path, **app_kwargs)

    return factory
