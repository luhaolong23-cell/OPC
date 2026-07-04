from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class SupportsSendMessage(Protocol):
    async def send_message(self, chatid: str, body: dict[str, Any]) -> dict[str, Any]: ...


class TextNotifier(Protocol):
    async def send_text(self, wecom_user_id: str, content: str) -> None: ...


@dataclass(slots=True)
class WecomTextNotifier:
    sender: SupportsSendMessage
    max_retries: int = 3

    async def send_text(self, wecom_user_id: str, content: str) -> None:
        last_error: Exception | None = None
        for _ in range(self.max_retries):
            try:
                await self.sender.send_message(
                    wecom_user_id,
                    {
                        "msgtype": "markdown",
                        "markdown": {"content": content},
                    },
                )
                return
            except Exception as exc:  # pragma: no cover - exercised through integration points
                last_error = exc
        if last_error is not None:
            raise last_error
