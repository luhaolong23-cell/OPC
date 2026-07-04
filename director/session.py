from __future__ import annotations

from dataclasses import dataclass

from workspace.manager import ActiveProjectExistsError, WorkspaceManager
from workspace.state import WechatSessionRecord


@dataclass(slots=True)
class DirectorSessionService:
    manager: WorkspaceManager

    def bind_active_project(self, wecom_user_id: str, project_id: str) -> WechatSessionRecord:
        return self.manager.bind_active_project(wecom_user_id, project_id)

    @staticmethod
    def active_project_id(session: WechatSessionRecord | None) -> str | None:
        if session is None:
            return None
        return session.active_project_id

    @staticmethod
    def ensure_can_start_project(session: WechatSessionRecord | None) -> None:
        if session is not None and session.active_project_id is not None:
            raise ActiveProjectExistsError(
                f"user {session.wecom_user_id!r} already has active project {session.active_project_id!r}"
            )
