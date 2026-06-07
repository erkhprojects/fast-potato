from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TaskProtocol(Protocol):
    name: str

    async def send(self, *args: Any, **kwargs: Any) -> Any: ...
    async def __call__(self, *args: Any, **kwargs: Any) -> Any: ...
