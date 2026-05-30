from __future__ import annotations

from collections.abc import Callable, Coroutine
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel

from ingestor.message import TaskMessage


def _serialize_arg(value: Any) -> Any:
    """Recursively serialize an argument to a JSON-safe structure."""
    if isinstance(value, BaseModel):
        return {"__pydantic__": type(value).__qualname__, "data": value.model_dump(mode="json")}
    if isinstance(value, list):
        return [_serialize_arg(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_arg(v) for k, v in value.items()}
    return value


class Task:
    def __init__(self, fn: Callable[..., Coroutine[Any, Any, Any]], name: str) -> None:
        self._fn = fn
        self.name = name

    async def send(
        self,
        *args: Any,
        delay: float | None = None,
        eta: datetime | None = None,
        **kwargs: Any,
    ) -> TaskMessage:
        if delay is not None and eta is not None:
            raise ValueError("Provide either 'delay' or 'eta', not both.")

        resolved_eta: datetime | None = eta
        if delay is not None:
            resolved_eta = datetime.now(tz=timezone.utc) + timedelta(seconds=delay)

        message = TaskMessage(
            task_name=self.name,
            args=[_serialize_arg(a) for a in args],
            kwargs={k: _serialize_arg(v) for k, v in kwargs.items()},
            eta=resolved_eta,
        )
        # broker publishing will be wired here in Phase 2
        return message

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return await self._fn(*args, **kwargs)
