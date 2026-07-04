from __future__ import annotations

import json
from pathlib import Path

from llm.client import _extract_json_object
from wecom_bot_bridge.client import WecomSdkBridgeClient


SAMPLES_DIR = Path(__file__).parent / "samples"


def test_wecom_sdk_text_message_sample_matches_bridge_parser_contract() -> None:
    frame = json.loads((SAMPLES_DIR / "wecom_text_message_frame.json").read_text())

    event = WecomSdkBridgeClient._to_text_message_event(frame)

    assert event.message_id == "req_123"
    assert event.wecom_user_id == "LuHaoLong"
    assert event.message == "开始开发这个项目"
    assert event.is_group_chat is False


def test_openai_json_markdown_sample_matches_llm_parser_contract() -> None:
    payload = _extract_json_object((SAMPLES_DIR / "openai_json_response.md").read_text())

    assert payload == {"summary": "ok", "open_questions": []}
