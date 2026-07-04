from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol
from uuid import uuid4

import httpx

from config import Settings


class NotificationPublishError(RuntimeError):
    """Raised when a notification cannot be delivered after retries."""


class NotificationPublisher(Protocol):
    def publish_event(
        self,
        *,
        event_type: str,
        project_id: str,
        wecom_user_id: str,
        message: str,
        status: str,
        checkpoint_type: str | None = None,
        event_id: str | None = None,
    ) -> str: ...


@dataclass(slots=True)
class NoopNotificationPublisher:
    def publish_event(
        self,
        *,
        event_type: str,
        project_id: str,
        wecom_user_id: str,
        message: str,
        status: str,
        checkpoint_type: str | None = None,
        event_id: str | None = None,
    ) -> str:
        return event_id or f"noop-{uuid4().hex}"


@dataclass(slots=True)
class HttpNotificationPublisher:
    notify_url: str
    token: str
    timeout_seconds: float = 5.0
    client: httpx.Client | None = None
    max_retries: int = 3
    event_id_factory: Callable[[], str] = field(default=lambda: uuid4().hex)

    def publish_event(
        self,
        *,
        event_type: str,
        project_id: str,
        wecom_user_id: str,
        message: str,
        status: str,
        checkpoint_type: str | None = None,
        event_id: str | None = None,
    ) -> str:
        event_id = event_id or self.event_id_factory()
        payload = {
            "event_id": event_id,
            "event_type": event_type,
            "project_id": project_id,
            "wecom_user_id": wecom_user_id,
            "message": message,
            "status": status,
            "checkpoint_type": checkpoint_type,
        }
        headers = {"Authorization": f"Bearer {self.token}"}
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self._post(payload=payload, headers=headers)
                response.raise_for_status()
                if not self._is_accepted(response):
                    raise NotificationPublishError(f"failed to publish notification {event_id}")
                return event_id
            except NotificationPublishError:
                raise
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_error = exc
                if attempt == self.max_retries:
                    break

        raise NotificationPublishError(f"failed to publish notification {event_id}") from last_error

    def _post(self, *, payload: dict[str, object], headers: dict[str, str]) -> httpx.Response:
        client = self.client or httpx.Client(trust_env=False)
        if client.__class__.__name__ == 'TestClient':
            return client.post(self.notify_url, json=payload, headers=headers)
        return client.post(
            self.notify_url,
            json=payload,
            headers=headers,
            timeout=self.timeout_seconds,
        )

    @staticmethod
    def _is_accepted(response: httpx.Response) -> bool:
        try:
            payload = response.json()
        except ValueError:
            return True
        accepted = payload.get("accepted")
        return accepted is not False



def build_notification_publisher(settings: Settings) -> NotificationPublisher:
    if not settings.wecom_bridge_notify_url or not settings.wecom_bridge_notify_token:
        return NoopNotificationPublisher()
    return HttpNotificationPublisher(
        notify_url=settings.wecom_bridge_notify_url,
        token=settings.wecom_bridge_notify_token,
        timeout_seconds=settings.wecom_notify_timeout,
    )
