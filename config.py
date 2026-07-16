from __future__ import annotations

from dataclasses import dataclass
from os import getenv
from pathlib import Path


def _default_sqlite_database_url() -> str:
    return f"sqlite:///{(Path(__file__).resolve().parent / 'opc.db').as_posix()}"


def _normalize_database_url(database_url: str) -> str:
    prefix = 'sqlite:///'
    if not database_url.startswith(prefix):
        return database_url
    location = database_url.removeprefix(prefix)
    if not location or location == ':memory:' or Path(location).is_absolute():
        return database_url
    project_root = Path(__file__).resolve().parent
    normalized = (project_root / location).resolve()
    return f"{prefix}{normalized.as_posix()}"


@dataclass(slots=True, frozen=True)
class Settings:
    app_name: str
    database_url: str
    workspace_root: Path
    wecom_agent_id: str | None
    wecom_corp_id: str | None
    wecom_corp_secret: str | None
    llm_model: str
    docker_prepare_timeout_seconds: int
    docker_test_timeout_seconds: int
    director_model: str | None = None
    pm_model: str | None = None
    planner_model: str | None = None
    coder_model: str | None = None
    debugger_model: str | None = None
    reviewer_model: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    wecom_bridge_notify_url: str | None = None
    wecom_bridge_notify_token: str | None = None
    wecom_notify_timeout: float = 5.0
    opc_internal_token: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        workspace_root = Path(getenv("OPC_WORKSPACE_ROOT", str(Path(__file__).resolve().parent / "new_project")))
        default_model = getenv("OPC_LLM_MODEL", "gpt-5")
        return cls(
            app_name=getenv("OPC_APP_NAME", "OPC Development"),
            database_url=_normalize_database_url(getenv("OPC_DATABASE_URL", _default_sqlite_database_url())),
            workspace_root=workspace_root,
            wecom_agent_id=getenv("WECOM_AGENT_ID"),
            wecom_corp_id=getenv("WECOM_CORP_ID"),
            wecom_corp_secret=getenv("WECOM_CORP_SECRET"),
            llm_model=default_model,
            docker_prepare_timeout_seconds=int(getenv("OPC_DOCKER_PREPARE_TIMEOUT", "120")),
            docker_test_timeout_seconds=int(getenv("OPC_DOCKER_TEST_TIMEOUT", "120")),
            director_model=getenv("OPC_DIRECTOR_MODEL", default_model),
            pm_model=getenv("OPC_PM_MODEL", default_model),
            planner_model=getenv("OPC_PLANNER_MODEL", default_model),
            coder_model=getenv("OPC_CODER_MODEL", default_model),
            debugger_model=getenv("OPC_DEBUGGER_MODEL", default_model),
            reviewer_model=getenv("OPC_REVIEWER_MODEL", default_model),
            openai_api_key=getenv("OPENAI_API_KEY"),
            openai_base_url=getenv("OPENAI_BASE_URL"),
            wecom_bridge_notify_url=getenv("WECOM_BRIDGE_NOTIFY_URL"),
            wecom_bridge_notify_token=getenv("WECOM_BRIDGE_NOTIFY_TOKEN"),
            wecom_notify_timeout=float(getenv("WECOM_NOTIFY_TIMEOUT", "5")),
            opc_internal_token=getenv("OPC_INTERNAL_TOKEN"),
        )
