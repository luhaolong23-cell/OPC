from __future__ import annotations

from dataclasses import dataclass, field

from wecom_bot_bridge.notifier import WecomTextNotifier


@dataclass
class RecordingSender:
    calls: list[tuple[str, dict]] = field(default_factory=list)

    async def send_message(self, chatid: str, body: dict) -> dict:
        self.calls.append((chatid, body))
        return {"ok": True}


async def _send(notifier: WecomTextNotifier, user_id: str, content: str) -> None:
    await notifier.send_text(user_id, content)


def test_wecom_text_notifier_uses_markdown_for_proactive_messages() -> None:
    import asyncio

    sender = RecordingSender()
    notifier = WecomTextNotifier(sender=sender)

    asyncio.run(_send(notifier, "alice", "项目已完成"))

    assert sender.calls == [
        (
            "alice",
            {
                "msgtype": "markdown",
                "markdown": {"content": "项目已完成"},
            },
        )
    ]
