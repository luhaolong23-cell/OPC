from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from llm.client import OpenAIJSONClient


@dataclass
class FakeResponse:
    output_text: str


@dataclass
class FakeResponsesAPI:
    outputs: list[str]
    calls: list[dict] = field(default_factory=list)

    def create(self, *, model: str, instructions: str, input: str):
        self.calls.append({"model": model, "instructions": instructions, "input": input})
        return FakeResponse(output_text=self.outputs.pop(0))


@dataclass
class FakeOpenAIClient:
    responses: FakeResponsesAPI


def test_openai_json_client_retries_once_when_first_response_is_not_json() -> None:
    fake_client = FakeOpenAIClient(
        responses=FakeResponsesAPI(outputs=["not json", '{"summary":"ok"}'])
    )
    client = OpenAIJSONClient(model="gpt-5", client=fake_client)

    result = client.generate_json(instructions="return json", input_text="hello")

    assert result == {"summary": "ok"}
    assert len(fake_client.responses.calls) == 2
    assert "valid JSON object" in fake_client.responses.calls[1]["instructions"]


def test_openai_json_client_raises_after_retry_exhausted() -> None:
    fake_client = FakeOpenAIClient(
        responses=FakeResponsesAPI(outputs=["still bad", "also bad"])
    )
    client = OpenAIJSONClient(model="gpt-5", client=fake_client)

    with pytest.raises(ValueError):
        client.generate_json(instructions="return json", input_text="hello")

    assert len(fake_client.responses.calls) == 2
