from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from core.potato import Potato
from core.protocols import TaskProtocol


class FastPotato:
    def __init__(self, name: str, potato: Potato | None = None) -> None:
        self.name = name
        self.potato = potato
        self._registry: dict[str, TaskProtocol] = {}

    def task(self, fn: Callable[..., Coroutine[Any, Any, Any]]) -> TaskProtocol:
        """Decorator that registers an async function as a task."""
        from ingestor.task import Task

        task_name = f"{self.name}.{fn.__qualname__}"
        t = Task(fn=fn, name=task_name)
        self._registry[task_name] = t
        return t

    def get_task(self, name: str) -> TaskProtocol:
        try:
            return self._registry[name]
        except KeyError:
            raise KeyError(f"Task '{name}' is not registered in app '{self.name}'.")
