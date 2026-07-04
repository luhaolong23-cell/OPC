from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi.testclient import TestClient


def build_feedback_payload(
    payload: Mapping[str, Any],
    *,
    action: str = "approve",
    comments: str = "",
    rejection_reason_type: str | None = None,
) -> dict[str, Any]:
    body = {
        "checkpoint_id": payload["checkpoint"]["id"],
        "checkpoint_type": payload["checkpoint"]["type"],
        "action": action,
        "comments": comments,
        "client_version": payload["project"]["version"],
    }
    if rejection_reason_type is not None:
        body["rejection_reason_type"] = rejection_reason_type
    return body


def create_project_and_run(
    client: TestClient,
    *,
    title: str = "Todo API",
    requirement: str = "Build a todo api.",
) -> tuple[str, dict[str, Any]]:
    create_response = client.post(
        "/projects",
        json={"title": title, "requirement": requirement},
    )
    project_id = create_response.json()["project"]["id"]
    run_response = client.post(f"/projects/{project_id}/run")
    return project_id, run_response.json()


def advance_to_plan_review(
    client: TestClient,
    *,
    title: str = "Todo API",
    requirement: str = "Build a todo api.",
) -> tuple[str, dict[str, Any]]:
    project_id, payload = create_project_and_run(client, title=title, requirement=requirement)
    response = client.post(
        f"/projects/{project_id}/feedback",
        json=build_feedback_payload(payload),
    )
    return project_id, response.json()


def advance_to_code_review(
    client: TestClient,
    *,
    title: str = "Todo API",
    requirement: str = "Build a todo api.",
) -> tuple[str, dict[str, Any]]:
    project_id, payload = advance_to_plan_review(client, title=title, requirement=requirement)
    response = client.post(
        f"/projects/{project_id}/feedback",
        json=build_feedback_payload(payload),
    )
    return project_id, response.json()
