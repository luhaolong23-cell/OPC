from __future__ import annotations

import httpx
import pytest

from notifications.publisher import HttpNotificationPublisher, NotificationPublishError


def test_http_notification_publisher_posts_notify_event_with_bearer_auth() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["payload"] = request.read().decode("utf-8")
        return httpx.Response(200, json={"accepted": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = HttpNotificationPublisher(
        notify_url="http://bridge/internal/notify",
        token="notify-token",
        timeout_seconds=3.0,
        client=client,
        event_id_factory=lambda: "evt-fixed",
    )

    event_id = publisher.publish_event(
        event_type="project_completed",
        project_id="proj_123",
        wecom_user_id="alice",
        message="项目已完成",
        status="done",
    )

    assert event_id == "evt-fixed"
    assert captured["url"] == "http://bridge/internal/notify"
    assert captured["auth"] == "Bearer notify-token"
    assert '"event_type":"project_completed"' in str(captured["payload"])


def test_http_notification_publisher_retries_timeout_then_succeeds() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise httpx.ConnectTimeout("timed out")
        return httpx.Response(200, json={"accepted": True})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = HttpNotificationPublisher(
        notify_url="http://bridge/internal/notify",
        token="notify-token",
        timeout_seconds=1.0,
        client=client,
        event_id_factory=lambda: "evt-timeout",
    )

    event_id = publisher.publish_event(
        event_type="checkpoint_ready",
        project_id="proj_123",
        wecom_user_id="alice",
        message="需要审批",
        status="wait_human_plan",
        checkpoint_type="plan_review",
    )

    assert event_id == "evt-timeout"
    assert attempts["count"] == 3


def test_http_notification_publisher_does_not_retry_when_bridge_rejects_delivery() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(200, json={"accepted": False})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    publisher = HttpNotificationPublisher(
        notify_url="http://bridge/internal/notify",
        token="notify-token",
        timeout_seconds=1.0,
        client=client,
        event_id_factory=lambda: "evt-rejected",
    )

    with pytest.raises(NotificationPublishError, match="evt-rejected"):
        publisher.publish_event(
            event_type="checkpoint_ready",
            project_id="proj_123",
            wecom_user_id="alice",
            message="需要审批",
            status="wait_human_requirement",
            checkpoint_type="requirement_review",
        )

    assert attempts["count"] == 1
