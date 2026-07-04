from agents.skills.registry import SkillRegistry
from config import Settings
from fastapi.testclient import TestClient
from mcp.mapping import LogicalToolMappingRegistry

from main import create_app


def _test_settings(tmp_path) -> Settings:
    return Settings(
        app_name="OPC Development",
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / "projects",
        wecom_agent_id=None,
        wecom_corp_id=None,
        wecom_corp_secret=None,
        llm_model="gpt-default",
        docker_prepare_timeout_seconds=120,
        docker_test_timeout_seconds=120,
        pm_model="gpt-pm",
        planner_model="gpt-planner",
        coder_model="gpt-coder",
        debugger_model="gpt-debugger",
        reviewer_model="gpt-reviewer",
    )


def test_create_app_exposes_health_endpoint() -> None:
    client = TestClient(create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_settings_from_env_reads_bridge_notification_configuration(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPC_DATABASE_URL", f"sqlite:///{tmp_path / 'opc.db'}")
    monkeypatch.setenv("OPC_WORKSPACE_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("WECOM_BRIDGE_NOTIFY_URL", "http://127.0.0.1:9001/internal/notify")
    monkeypatch.setenv("WECOM_BRIDGE_NOTIFY_TOKEN", "notify-token")
    monkeypatch.setenv("WECOM_NOTIFY_TIMEOUT", "9.5")
    monkeypatch.setenv("OPC_INTERNAL_TOKEN", "opc-token")

    settings = Settings.from_env()

    assert settings.wecom_bridge_notify_url == "http://127.0.0.1:9001/internal/notify"
    assert settings.wecom_bridge_notify_token == "notify-token"
    assert settings.wecom_notify_timeout == 9.5
    assert settings.opc_internal_token == "opc-token"


def test_settings_from_env_reads_per_agent_models(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPC_DATABASE_URL", f"sqlite:///{tmp_path / 'opc.db'}")
    monkeypatch.setenv("OPC_WORKSPACE_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("OPC_LLM_MODEL", "gpt-default")
    monkeypatch.setenv("OPC_PM_MODEL", "gpt-pm")
    monkeypatch.setenv("OPC_PLANNER_MODEL", "gpt-planner")
    monkeypatch.setenv("OPC_CODER_MODEL", "gpt-coder")
    monkeypatch.setenv("OPC_DEBUGGER_MODEL", "gpt-debugger")
    monkeypatch.setenv("OPC_REVIEWER_MODEL", "gpt-reviewer")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.com/v1")

    settings = Settings.from_env()

    assert settings.llm_model == "gpt-default"
    assert settings.pm_model == "gpt-pm"
    assert settings.planner_model == "gpt-planner"
    assert settings.coder_model == "gpt-coder"
    assert settings.debugger_model == "gpt-debugger"
    assert settings.reviewer_model == "gpt-reviewer"
    assert settings.openai_api_key == "sk-test"
    assert settings.openai_base_url == "https://example.com/v1"


def test_create_app_wires_per_agent_models(tmp_path) -> None:
    app = create_app(settings=_test_settings(tmp_path))
    workflow_service = app.state.workflow_service

    assert workflow_service.pm_agent.model == "gpt-pm"
    assert workflow_service.planner_agent.model == "gpt-planner"
    assert workflow_service.coder_agent.model == "gpt-coder"
    assert workflow_service.debugger_agent.model == "gpt-debugger"
    assert workflow_service.reviewer_agent.model == "gpt-reviewer"


def test_create_app_wires_agent_capabilities(tmp_path) -> None:
    app = create_app(settings=_test_settings(tmp_path))
    workflow_service = app.state.workflow_service

    assert workflow_service.pm_agent.profile is not None
    assert workflow_service.pm_agent.profile.name == "pm"
    assert set(workflow_service.coder_agent.skills) == {"coder.implement", "coder.tdd", "coder.spec_driven"}
    assert set(workflow_service.coder_agent.tools.tools) == {
        "repo_reader",
        "patch_applier",
        "test_runner",
    }


def test_create_app_exposes_runtime_tool_registry_with_policy_and_provider_mappings(tmp_path) -> None:
    app = create_app(settings=_test_settings(tmp_path))

    tool_registry = app.state.tool_registry

    assert tool_registry.policy_engine is not None
    assert tool_registry.provider_registry is not None
    assert tool_registry.provider_registry.mcp_registry is not None
    assert tool_registry.provider_registry.mappings is not None


def test_create_app_can_wire_custom_skill_registry_into_agents(tmp_path) -> None:
    skill_registry = SkillRegistry.from_file("tests/contracts/samples/skill_sources_override_config.json")

    app = create_app(settings=_test_settings(tmp_path), skill_registry=skill_registry)

    assert app.state.workflow_service.pm_agent.skills["pm.discovery"].metadata["source"] == "codex-skill"




class LifecycleTrackingToolRegistry:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.provider_registry = type(
            "FakeProviderRegistry",
            (),
            {"mappings": LogicalToolMappingRegistry.from_file("config/mappings/logical_tools.yaml")},
        )()

    def start(self) -> None:
        self.events.append("start")

    def stop(self) -> None:
        self.events.append("stop")

    def health_snapshot(self) -> dict[str, dict[str, object]]:
        return {
            "context7": {"healthy": True, "error": None},
        }

    def list_tool_specs(self) -> list[object]:
        from tools.specs import ToolSpec

        return [
            ToolSpec(
                name="docs.search",
                version="1.0",
                description="Search docs.",
                capability_tags=("docs.search",),
                input_schema={"type": "object"},
                output_schema={},
                side_effect_level="read",
                provider="context7",
                metadata={"remote_tool": "search_docs"},
            )
        ]


def test_create_app_starts_and_stops_tool_registry_with_lifespan(tmp_path) -> None:
    registry = LifecycleTrackingToolRegistry()

    with TestClient(
        create_app(
            settings=_test_settings(tmp_path),
            tool_registry=registry,
            skill_registry=SkillRegistry.from_file("tests/contracts/samples/skill_sources_override_config.json"),
            workflow_service=object(),
            wechat_message_service=object(),
        )
    ):
        assert registry.events == ["start"]

    assert registry.events == ["start", "stop"]




def test_create_app_exposes_runtime_health_snapshot_endpoint(tmp_path) -> None:
    registry = LifecycleTrackingToolRegistry()

    with TestClient(
        create_app(
            settings=_test_settings(tmp_path),
            tool_registry=registry,
            skill_registry=SkillRegistry.from_file("tests/contracts/samples/skill_sources_override_config.json"),
            workflow_service=object(),
            wechat_message_service=object(),
        )
    ) as client:
        response = client.get("/healthz/runtime")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "ready": True,
        "providers": {
            "context7": {"healthy": True, "error": None},
        },
        "tools": [
            {
                "name": "docs.search",
                "provider": "context7",
                "capability_tags": ["docs.search"],
                "side_effect_level": "read",
            }
        ],
        "mappings": [
            {
                "logical_tool": "docs.search",
                "providers": [
                    {"server": "context7", "remote_tool": "search_docs", "priority": 100},
                    {"server": "local_docs", "remote_tool": "repo_search", "priority": 50},
                ],
            }
        ],
        "skill_sources": [
            {"name": "codex", "skill_count": 1},
            {"name": "builtin", "skill_count": 15},
        ],
    }






class UnhealthyLifecycleTrackingToolRegistry(LifecycleTrackingToolRegistry):
    def health_snapshot(self) -> dict[str, dict[str, object]]:
        return {
            "context7": {"healthy": False, "error": "down"},
        }


def test_create_app_exposes_runtime_readiness_false_when_provider_is_unhealthy(tmp_path) -> None:
    registry = UnhealthyLifecycleTrackingToolRegistry()

    with TestClient(
        create_app(
            settings=_test_settings(tmp_path),
            tool_registry=registry,
            workflow_service=object(),
            wechat_message_service=object(),
        )
    ) as client:
        response = client.get("/healthz/runtime")

    assert response.status_code == 200
    assert response.json()["ready"] is False
    assert response.json()["providers"] == {"context7": {"healthy": False, "error": "down"}}


def test_create_app_uses_default_skill_registry_for_runtime_diagnostics(tmp_path) -> None:
    registry = LifecycleTrackingToolRegistry()

    with TestClient(
        create_app(
            settings=_test_settings(tmp_path),
            tool_registry=registry,
            workflow_service=object(),
            wechat_message_service=object(),
        )
    ) as client:
        response = client.get("/healthz/runtime")

    assert response.status_code == 200
    assert response.json()["skill_sources"] == [{"name": "builtin", "skill_count": 15}]


def test_settings_from_env_reads_director_model(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPC_DATABASE_URL", f"sqlite:///{tmp_path / 'opc.db'}")
    monkeypatch.setenv("OPC_WORKSPACE_ROOT", str(tmp_path / "projects"))
    monkeypatch.setenv("OPC_LLM_MODEL", "gpt-default")
    monkeypatch.setenv("OPC_DIRECTOR_MODEL", "gpt-director")

    settings = Settings.from_env()

    assert settings.director_model == "gpt-director"


def test_create_app_wires_director_model(tmp_path) -> None:
    settings = Settings(
        app_name="OPC Development",
        database_url=f"sqlite:///{tmp_path / 'opc.db'}",
        workspace_root=tmp_path / "projects",
        wecom_agent_id=None,
        wecom_corp_id=None,
        wecom_corp_secret=None,
        llm_model="gpt-default",
        docker_prepare_timeout_seconds=120,
        docker_test_timeout_seconds=120,
        director_model="gpt-director",
    )

    app = create_app(settings=settings)

    assert app.state.director_router.agent is not None
    assert app.state.director_router.agent.model == "gpt-director"
