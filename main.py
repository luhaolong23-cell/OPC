from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from agents.factory import build_agent
from agents.skills.registry import SkillRegistry, get_default_registry
from api.routes import router
from config import Settings
from director.router import DirectorRouter
from director.wechat_message_service import WechatMessageService
from graph.runtime import WorkflowService
from llm import OpenAIJSONClient
from notifications.publisher import NotificationPublisher, build_notification_publisher
from tools.defaults import build_default_tool_registry
from tools.registry import ToolRegistry
from tools.sandbox import DockerSandbox
from workspace.manager import WorkspaceManager


def _build_llm_client(model: str, settings: Settings) -> OpenAIJSONClient | None:
    if not settings.openai_api_key:
        return None
    return OpenAIJSONClient(
        model=model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
    )


def create_app(
    *,
    settings: Settings | None = None,
    workspace_manager: WorkspaceManager | None = None,
    director_router: DirectorRouter | None = None,
    pm_agent: object | None = None,
    planner_agent: object | None = None,
    coder_agent: object | None = None,
    debugger_agent: object | None = None,
    reviewer_agent: object | None = None,
    sandbox: object | None = None,
    workflow_service: WorkflowService | None = None,
    wechat_message_service: WechatMessageService | None = None,
    notification_publisher: NotificationPublisher | None = None,
    tool_registry: ToolRegistry | None = None,
    skill_registry: SkillRegistry | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    workspace_manager = workspace_manager or WorkspaceManager(database_url=settings.database_url, workspace_root=settings.workspace_root)
    workspace_manager.initialize()
    sandbox = sandbox or DockerSandbox()
    tool_registry = tool_registry or build_default_tool_registry(sandbox=sandbox)
    skill_registry = skill_registry or get_default_registry()

    director_model = settings.director_model or settings.llm_model
    director_router = director_router or DirectorRouter(
        agent=build_agent('director', model=director_model, llm_client=_build_llm_client(director_model, settings), tool_registry=tool_registry, skill_registry=skill_registry)
    )
    notification_publisher = notification_publisher or build_notification_publisher(settings)
    pm_model = settings.pm_model or settings.llm_model
    planner_model = settings.planner_model or settings.llm_model
    coder_model = settings.coder_model or settings.llm_model
    debugger_model = settings.debugger_model or settings.llm_model
    reviewer_model = settings.reviewer_model or settings.llm_model
    workflow_service = workflow_service or WorkflowService(
        manager=workspace_manager,
        pm_agent=pm_agent or build_agent("pm", model=pm_model, llm_client=_build_llm_client(pm_model, settings), tool_registry=tool_registry, skill_registry=skill_registry),
        planner_agent=planner_agent or build_agent("planner", model=planner_model, llm_client=_build_llm_client(planner_model, settings), tool_registry=tool_registry, skill_registry=skill_registry),
        coder_agent=coder_agent or build_agent("coder", model=coder_model, llm_client=_build_llm_client(coder_model, settings), tool_registry=tool_registry, skill_registry=skill_registry),
        debugger_agent=debugger_agent or build_agent("debugger", model=debugger_model, llm_client=_build_llm_client(debugger_model, settings), tool_registry=tool_registry, skill_registry=skill_registry),
        reviewer_agent=reviewer_agent or build_agent("reviewer", model=reviewer_model, llm_client=_build_llm_client(reviewer_model, settings), tool_registry=tool_registry, skill_registry=skill_registry),
        sandbox=sandbox,
        notification_publisher=notification_publisher,
    )
    wechat_message_service = wechat_message_service or WechatMessageService(
        manager=workspace_manager,
        director_router=director_router,
        workflow_service=workflow_service,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if hasattr(tool_registry, "start"):
            tool_registry.start()
        try:
            yield
        finally:
            if hasattr(tool_registry, "stop"):
                tool_registry.stop()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.settings = settings
    app.state.workspace_manager = workspace_manager
    app.state.director_router = director_router
    app.state.workflow_service = workflow_service
    app.state.wechat_message_service = wechat_message_service
    app.state.notification_publisher = notification_publisher
    app.state.tool_registry = tool_registry
    app.state.skill_registry = skill_registry
    app.include_router(router)
    return app
