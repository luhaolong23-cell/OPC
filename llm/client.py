from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from observability import wrap_openai_client


class StructuredLLMClient(Protocol):
    def generate_json(self, *, instructions: str, input_text: str) -> dict[str, Any]:
        ...


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    payload = json.loads(cleaned)
    if not isinstance(payload, dict):
        raise ValueError("LLM response must be a JSON object")
    return payload


@dataclass(slots=True)
class OpenAIJSONClient:
    model: str
    api_key: str | None = None
    base_url: str | None = None
    client: Any | None = None
    max_parse_attempts: int = 2

    def __post_init__(self) -> None:
        if self.client is None:
            from openai import OpenAI

            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.client = wrap_openai_client(self.client)

    def generate_json(self, *, instructions: str, input_text: str) -> dict[str, Any]:
        last_error: ValueError | None = None
        attempt_instructions = instructions
        for attempt in range(1, self.max_parse_attempts + 1):
            response = self.client.responses.create(
                model=self.model,
                instructions=attempt_instructions,
                input=input_text,
            )
            try:
                return _extract_json_object(response.output_text)
            except ValueError as exc:
                last_error = exc
                if attempt == self.max_parse_attempts:
                    break
                attempt_instructions = (
                    f"{instructions}\n"
                    "Return only a valid JSON object. Do not include markdown fences or explanatory text."
                )
        if last_error is not None:
            raise last_error
        raise ValueError('LLM response must be a JSON object')
