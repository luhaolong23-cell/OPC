from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from wecom_bot_bridge.models import TextMessageEvent


class OpcUserVisibleError(RuntimeError):
    """Raised when OPC returns an error detail that should be shown to the user."""


@dataclass(slots=True)
class OpcHttpClient:
    base_url: str
    token: str | None
    timeout_seconds: float = 10.0
    client: httpx.AsyncClient | None = None
    transport: httpx.AsyncBaseTransport | None = None

    async def forward_text_event(self, event: TextMessageEvent) -> dict[str, Any]:
        response = await self._request(
            "POST",
            "/wechat/events",
            json={
                "wecom_user_id": event.wecom_user_id,
                "message": event.message,
                "is_group_chat": event.is_group_chat,
            },
        )
        return response.json()

    async def start_project_run(self, project_id: str) -> None:
        await self._request("POST", f"/projects/{project_id}/run")

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        kwargs["headers"] = headers

        try:
            if self.client is not None:
                response = await self.client.request(method, path, timeout=self.timeout_seconds, **kwargs)
                response.raise_for_status()
                return response

            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.request(method, path, **kwargs)
                response.raise_for_status()
                return response
        except httpx.HTTPStatusError as exc:
            detail = self._extract_detail(exc.response)
            if exc.response.status_code < 500 and detail is not None:
                raise OpcUserVisibleError(detail) from exc
            raise

    @staticmethod
    def _extract_detail(response: httpx.Response) -> str | None:
        try:
            payload = response.json()
        except ValueError:
            text = response.text.strip()
            return text or None
        detail = payload.get("detail")
        if isinstance(detail, str):
            normalized = detail.strip()
            return normalized or None
        return None
