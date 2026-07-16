from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class _NoopTrace:
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def end(self, *, outputs: Any | None = None) -> None:
        return None


def wrap_openai_client(client: Any) -> Any:
    try:
        from langsmith.wrappers import wrap_openai
    except ImportError:
        return client
    try:
        return wrap_openai(client)
    except AttributeError:
        return client


@contextmanager
def trace_span(
    *,
    name: str,
    run_type: str = "chain",
    inputs: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    project_name: str | None = None,
) -> Iterator[Any]:
    try:
        import langsmith as ls
    except ImportError:
        yield _NoopTrace(metadata=dict(metadata or {}), tags=list(tags or []))
        return

    with ls.trace(
        name=name,
        run_type=run_type,
        inputs=inputs,
        metadata=metadata,
        tags=tags,
        project_name=project_name,
    ) as run_tree:
        yield run_tree
