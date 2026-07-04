from __future__ import annotations

from fastapi import Request

from config import Settings
from director.router import DirectorRouter
from director.wechat_message_service import WechatMessageService
from graph.runtime import WorkflowService
from workspace.manager import WorkspaceManager


def get_workspace_manager(request: Request) -> WorkspaceManager:
    return request.app.state.workspace_manager


def get_director_router(request: Request) -> DirectorRouter:
    return request.app.state.director_router


def get_workflow_service(request: Request) -> WorkflowService:
    return request.app.state.workflow_service


def get_wechat_message_service(request: Request) -> WechatMessageService:
    return request.app.state.wechat_message_service


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_notification_publisher(request: Request):
    return request.app.state.notification_publisher
