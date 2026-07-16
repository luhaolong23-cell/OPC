from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from api.dependencies import get_settings, get_wechat_message_service, get_workflow_service, get_workspace_manager
from api.schemas import (
    CheckpointResponse,
    CreateProjectEnvelope,
    CreateProjectRequest,
    FeedbackRequest,
    FeedbackResponse,
    ProjectResponse,
    ProjectRunResponse,
    WechatCardCallbackRequest,
    WechatEventRequest,
    WechatEventResponse,
)
from config import Settings
from director.router import UnsupportedConversationError
from director.wechat_message_service import WechatMessageService
from graph.runtime import FeedbackConflictError, WorkflowService
from workspace.manager import WorkspaceManager
from workspace.state import CheckpointRecord, ProjectRecord

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / 'ui' / 'templates'))


@router.get('/healthz')
def healthz() -> dict[str, str]:
    return {'status': 'ok'}

@router.get('/healthz/runtime')
def runtime_healthz(request: Request) -> dict[str, object]:
    tool_registry = getattr(request.app.state, 'tool_registry', None)
    skill_registry = getattr(request.app.state, 'skill_registry', None)
    providers = tool_registry.health_snapshot() if tool_registry is not None and hasattr(tool_registry, 'health_snapshot') else {}
    tool_specs = tool_registry.list_tool_specs() if tool_registry is not None and hasattr(tool_registry, 'list_tool_specs') else []
    skill_sources = []
    if skill_registry is not None and hasattr(skill_registry, 'sources'):
        for source in skill_registry.sources:
            names = source.list_names() if hasattr(source, 'list_names') else ()
            skill_sources.append({'name': source.name, 'skill_count': len(names)})
    ready = all(provider.get('healthy', False) for provider in providers.values()) if providers else True
    return {
        'status': 'ok',
        'ready': ready,
        'providers': providers,
        'tools': [
            {
                'name': spec.name,
                'provider': spec.provider,
                'capability_tags': list(spec.capability_tags),
                'side_effect_level': spec.side_effect_level,
            }
            for spec in tool_specs
        ],
        'skill_sources': skill_sources,
    }



@router.post('/projects', response_model=CreateProjectEnvelope, status_code=status.HTTP_201_CREATED)
def create_project(payload: CreateProjectRequest, manager: WorkspaceManager = Depends(get_workspace_manager)) -> CreateProjectEnvelope:
    title = payload.title or payload.requirement
    project = manager.create_project(title=title, requirement=payload.requirement)
    return CreateProjectEnvelope(project=_to_project_response(project))


@router.post('/projects/{project_id}/run', response_model=ProjectRunResponse)
def run_project(
    project_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    workflow_service: WorkflowService = Depends(get_workflow_service),
) -> ProjectRunResponse:
    _require_internal_token(request, settings)
    try:
        project, checkpoint = workflow_service.start_project(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='project not found') from exc
    return ProjectRunResponse(project=_to_project_response(project), checkpoint=_to_checkpoint_response(checkpoint))


@router.get('/projects/{project_id}', response_model=CreateProjectEnvelope)
def get_project(project_id: str, manager: WorkspaceManager = Depends(get_workspace_manager)) -> CreateProjectEnvelope:
    project = manager.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='project not found')
    return CreateProjectEnvelope(project=_to_project_response(project))


@router.get('/projects/{project_id}/events')
def project_events(project_id: str, manager: WorkspaceManager = Depends(get_workspace_manager)) -> StreamingResponse:
    project = manager.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='project not found')

    def event_stream():
        payload = {'project_id': project.id, 'status': project.status.value, 'current_checkpoint_id': project.current_checkpoint_id}
        yield f"event: project.updated\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type='text/event-stream')


@router.post('/projects/{project_id}/feedback', response_model=FeedbackResponse)
def submit_feedback(project_id: str, payload: FeedbackRequest, workflow_service: WorkflowService = Depends(get_workflow_service)) -> FeedbackResponse:
    try:
        project, checkpoint = workflow_service.apply_feedback(
            project_id=project_id,
            checkpoint_id=payload.checkpoint_id,
            checkpoint_type=payload.checkpoint_type,
            action=payload.action,
            comments=payload.comments,
            rejection_reason_type=payload.rejection_reason_type,
            client_version=payload.client_version,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='project not found') from exc
    except FeedbackConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return FeedbackResponse(accepted=True, project=_to_project_response(project), checkpoint=_to_checkpoint_response(checkpoint))


@router.post('/wechat/card-callback', response_model=FeedbackResponse)
def receive_wechat_card_callback(payload: WechatCardCallbackRequest, workflow_service: WorkflowService = Depends(get_workflow_service)) -> FeedbackResponse:
    try:
        project, checkpoint = workflow_service.apply_feedback(
            project_id=payload.project_id,
            checkpoint_id=payload.checkpoint_id,
            checkpoint_type=payload.checkpoint_type,
            action=payload.action,
            comments=payload.comments,
            rejection_reason_type=payload.rejection_reason_type,
            client_version=payload.client_version,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='project not found') from exc
    except FeedbackConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return FeedbackResponse(accepted=True, project=_to_project_response(project), checkpoint=_to_checkpoint_response(checkpoint))


@router.post('/wechat/events', response_model=WechatEventResponse)
def receive_wechat_event(
    payload: WechatEventRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    wechat_message_service: WechatMessageService = Depends(get_wechat_message_service),
) -> WechatEventResponse:
    _require_internal_token(request, settings)
    try:
        return wechat_message_service.handle_message(
            wecom_user_id=payload.wecom_user_id,
            message=payload.message,
            is_group_chat=payload.is_group_chat,
        )
    except UnsupportedConversationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get('/debug/projects', response_class=HTMLResponse)
def debug_projects(request: Request, manager: WorkspaceManager = Depends(get_workspace_manager)) -> HTMLResponse:
    return templates.TemplateResponse(request, 'index.html', {'title': '项目列表', 'projects': manager.list_projects()})


@router.get('/debug/projects/{project_id}', response_class=HTMLResponse)
def debug_project_detail(project_id: str, request: Request, manager: WorkspaceManager = Depends(get_workspace_manager)) -> HTMLResponse:
    project = manager.get_project(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='project not found')
    checkpoint = manager.get_checkpoint(project.current_checkpoint_id) if project.current_checkpoint_id else None
    return templates.TemplateResponse(request, 'project_detail.html', {'title': project.title, 'project': project, 'checkpoint': checkpoint})



def _require_internal_token(request: Request, settings: Settings) -> None:
    if not settings.opc_internal_token:
        return
    authorization = request.headers.get('authorization')
    if authorization != f'Bearer {settings.opc_internal_token}':
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='invalid bearer token')



def _to_project_response(project: ProjectRecord) -> ProjectResponse:
    return ProjectResponse(
        id=project.id,
        title=project.title,
        requirement=project.requirement,
        status=project.status.value,
        version=project.version,
        current_checkpoint_id=project.current_checkpoint_id,
        requires_human_takeover=project.requires_human_takeover,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )



def _to_checkpoint_response(checkpoint: CheckpointRecord | None) -> CheckpointResponse | None:
    if checkpoint is None:
        return None
    return CheckpointResponse(
        id=checkpoint.id,
        project_id=checkpoint.project_id,
        type=checkpoint.type,
        status=checkpoint.status,
        available_actions=checkpoint.available_actions,
        created_at=checkpoint.created_at,
        resolved_at=checkpoint.resolved_at,
    )
