from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, String, Text, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.orm.session import sessionmaker as SessionMaker

from workspace.state import (
    CheckpointRecord,
    ProjectRecord,
    SessionMode,
    TaskStatus,
    WechatSessionRecord,
    utcnow,
)


class ActiveProjectExistsError(RuntimeError):
    """Raised when a user already has another active project."""


class Base(DeclarativeBase):
    pass


class ProjectModel(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    requirement: Mapped[str] = mapped_column(String)
    status: Mapped[TaskStatus] = mapped_column(SqlEnum(TaskStatus))
    version: Mapped[int]
    current_checkpoint_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requires_human_takeover: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True))


class WechatSessionModel(Base):
    __tablename__ = "wechat_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    wecom_user_id: Mapped[str] = mapped_column(String(255), unique=True)
    mode: Mapped[SessionMode] = mapped_column(SqlEnum(SessionMode))
    active_project_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    conversation_summary: Mapped[str] = mapped_column(String, default="")
    last_requirement_draft: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True))


class CheckpointModel(Base):
    __tablename__ = "checkpoints"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    available_actions_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)


@dataclass(slots=True)
class WorkspaceManager:
    database_url: str
    workspace_root: Path
    _engine: Engine = field(init=False, repr=False)
    _session_factory: SessionMaker[Session] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.workspace_root = Path(self.workspace_root)
        self._engine = create_engine(self.database_url, future=True)
        self._session_factory = sessionmaker(self._engine, expire_on_commit=False)

    def initialize(self) -> None:
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(self._engine)

    def project_root(self, project_id: str) -> Path:
        return self.workspace_root / project_id

    def project_workspace_path(self, project_id: str) -> Path:
        return self.project_root(project_id) / "workspace"

    def create_project(self, title: str, requirement: str) -> ProjectRecord:
        now = utcnow()
        model = ProjectModel(
            id=uuid4().hex,
            title=title,
            requirement=requirement,
            status=TaskStatus.DISCOVERY,
            version=1,
            current_checkpoint_id=None,
            requires_human_takeover=False,
            created_at=now,
            updated_at=now,
        )
        with self._session() as session:
            session.add(model)
            session.commit()
        self.project_workspace_path(model.id).mkdir(parents=True, exist_ok=True)
        return self._to_project_record(model)

    def persist_code_files(self, project_id: str, code_files: dict[str, str]) -> Path:
        workspace_path = self.project_workspace_path(project_id)
        workspace_path.mkdir(parents=True, exist_ok=True)
        for relative_path, content in code_files.items():
            file_path = workspace_path / relative_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content)
        return workspace_path

    def list_projects(self) -> list[ProjectRecord]:
        with self._session() as session:
            models = session.scalars(select(ProjectModel).order_by(ProjectModel.created_at.desc())).all()
            return [self._to_project_record(model) for model in models]

    def get_project(self, project_id: str) -> ProjectRecord | None:
        with self._session() as session:
            model = session.get(ProjectModel, project_id)
            if model is None:
                return None
            return self._to_project_record(model)

    def get_session(self, wecom_user_id: str) -> WechatSessionRecord | None:
        with self._session() as session:
            model = session.scalar(
                select(WechatSessionModel).where(WechatSessionModel.wecom_user_id == wecom_user_id)
            )
            if model is None:
                return None
            return self._to_session_record(model)

    def upsert_chat_session(
        self,
        wecom_user_id: str,
        *,
        conversation_summary: str | None = None,
        requirement_draft: str | None = None,
    ) -> WechatSessionRecord:
        now = utcnow()
        with self._session() as session:
            existing = session.scalar(
                select(WechatSessionModel).where(WechatSessionModel.wecom_user_id == wecom_user_id)
            )
            if existing is not None:
                if existing.active_project_id is None:
                    existing.mode = SessionMode.CHAT
                if conversation_summary is not None:
                    existing.conversation_summary = conversation_summary
                if requirement_draft is not None:
                    existing.last_requirement_draft = requirement_draft
                existing.updated_at = now
                session.commit()
                return self._to_session_record(existing)

            created = WechatSessionModel(
                id=uuid4().hex,
                wecom_user_id=wecom_user_id,
                mode=SessionMode.CHAT,
                active_project_id=None,
                conversation_summary=conversation_summary or "",
                last_requirement_draft=requirement_draft,
                created_at=now,
                updated_at=now,
            )
            session.add(created)
            session.commit()
            return self._to_session_record(created)

    def bind_active_project(self, wecom_user_id: str, project_id: str) -> WechatSessionRecord:
        now = utcnow()
        with self._session() as session:
            existing = session.scalar(
                select(WechatSessionModel).where(WechatSessionModel.wecom_user_id == wecom_user_id)
            )
            if existing is not None:
                if existing.active_project_id not in (None, project_id):
                    raise ActiveProjectExistsError(
                        f"user {wecom_user_id!r} already has active project {existing.active_project_id!r}"
                    )
                existing.mode = SessionMode.PROJECT_ACTIVE
                existing.active_project_id = project_id
                existing.updated_at = now
                session.commit()
                return self._to_session_record(existing)

            created = WechatSessionModel(
                id=uuid4().hex,
                wecom_user_id=wecom_user_id,
                mode=SessionMode.PROJECT_ACTIVE,
                active_project_id=project_id,
                conversation_summary="",
                last_requirement_draft=None,
                created_at=now,
                updated_at=now,
            )
            session.add(created)
            session.commit()
            return self._to_session_record(created)

    def find_wecom_user_id_by_project(self, project_id: str) -> str | None:
        with self._session() as session:
            model = session.scalar(
                select(WechatSessionModel).where(WechatSessionModel.active_project_id == project_id)
            )
            return model.wecom_user_id if model is not None else None

    def create_checkpoint(
        self,
        *,
        project_id: str,
        checkpoint_type: str,
        available_actions: list[str],
    ) -> CheckpointRecord:
        now = utcnow()
        model = CheckpointModel(
            id=uuid4().hex,
            project_id=project_id,
            type=checkpoint_type,
            status="pending",
            available_actions_json=json.dumps(available_actions),
            created_at=now,
            resolved_at=None,
        )
        with self._session() as session:
            project = session.get(ProjectModel, project_id)
            if project is None:
                raise KeyError(project_id)
            project.current_checkpoint_id = model.id
            project.version += 1
            project.updated_at = now
            session.add(model)
            session.commit()
        return self._to_checkpoint_record(model)

    def get_checkpoint(self, checkpoint_id: str) -> CheckpointRecord | None:
        with self._session() as session:
            model = session.get(CheckpointModel, checkpoint_id)
            if model is None:
                return None
            return self._to_checkpoint_record(model)

    def resolve_checkpoint(self, checkpoint_id: str) -> CheckpointRecord:
        now = utcnow()
        with self._session() as session:
            model = session.get(CheckpointModel, checkpoint_id)
            if model is None:
                raise KeyError(checkpoint_id)
            model.status = "resolved"
            model.resolved_at = now
            session.commit()
            return self._to_checkpoint_record(model)

    def update_project_flow_state(
        self,
        project_id: str,
        *,
        status: TaskStatus,
        current_checkpoint_id: str | None,
    ) -> ProjectRecord:
        now = utcnow()
        with self._session() as session:
            project = session.get(ProjectModel, project_id)
            if project is None:
                raise KeyError(project_id)
            project.status = status
            project.current_checkpoint_id = current_checkpoint_id
            project.version += 1
            project.updated_at = now
            if status in {TaskStatus.DONE, TaskStatus.CANCELLED, TaskStatus.FAILED}:
                bound_sessions = session.scalars(
                    select(WechatSessionModel).where(WechatSessionModel.active_project_id == project_id)
                ).all()
                for bound_session in bound_sessions:
                    bound_session.mode = SessionMode.CHAT
                    bound_session.active_project_id = None
                    bound_session.updated_at = now
            session.commit()
            return self._to_project_record(project)

    def refresh_active_project_requirement(self, project_id: str, *, title: str, requirement: str) -> ProjectRecord:
        now = utcnow()
        with self._session() as session:
            project = session.get(ProjectModel, project_id)
            if project is None:
                raise KeyError(project_id)
            if project.current_checkpoint_id is not None:
                checkpoint = session.get(CheckpointModel, project.current_checkpoint_id)
                if checkpoint is not None and checkpoint.status == "pending":
                    checkpoint.status = "resolved"
                    checkpoint.resolved_at = now
            project.title = title
            project.requirement = requirement
            project.status = TaskStatus.DISCOVERY
            project.current_checkpoint_id = None
            project.version += 1
            project.updated_at = now
            session.commit()
            return self._to_project_record(project)

    def _session(self) -> Session:
        return self._session_factory()

    @staticmethod
    def _to_project_record(model: ProjectModel) -> ProjectRecord:
        return ProjectRecord(
            id=model.id,
            title=model.title,
            requirement=model.requirement,
            status=model.status,
            version=model.version,
            current_checkpoint_id=model.current_checkpoint_id,
            requires_human_takeover=model.requires_human_takeover,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_session_record(model: WechatSessionModel) -> WechatSessionRecord:
        return WechatSessionRecord(
            id=model.id,
            wecom_user_id=model.wecom_user_id,
            mode=model.mode,
            active_project_id=model.active_project_id,
            conversation_summary=model.conversation_summary,
            last_requirement_draft=model.last_requirement_draft,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def _to_checkpoint_record(model: CheckpointModel) -> CheckpointRecord:
        return CheckpointRecord(
            id=model.id,
            project_id=model.project_id,
            type=model.type,
            status=model.status,
            available_actions=json.loads(model.available_actions_json),
            created_at=model.created_at,
            resolved_at=model.resolved_at,
        )
