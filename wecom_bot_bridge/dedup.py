from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class TtlDeduplicator:
    ttl_seconds: float = 300.0
    _entries: dict[str, float] = field(default_factory=dict)

    def seen(self, key: str) -> bool:
        self._purge_expired()
        expires_at = self._entries.get(key)
        return expires_at is not None and expires_at > time.monotonic()

    def mark(self, key: str) -> None:
        self._purge_expired()
        self._entries[key] = time.monotonic() + self.ttl_seconds

    def _purge_expired(self) -> None:
        now = time.monotonic()
        expired = [key for key, expires_at in self._entries.items() if expires_at <= now]
        for key in expired:
            self._entries.pop(key, None)
