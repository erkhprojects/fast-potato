from __future__ import annotations

import importlib
from collections.abc import Callable, Coroutine
from typing import Any

from fast_potato import schedule
from fast_potato.task import Task


class FastPotato:
    def __init__(
        self,
        name: str,
        broker: Any,
        potato: Any = None,
        schedules: list[schedule.Schedule] | None = None,
        include: list[str] | None = None,
    ) -> None:
        if broker is None:
            raise ValueError(
                "FastPotato requires a broker. "
                "Pass one at init: FastPotato('name', broker=RedisBroker(...)). "
                "For tests and local dev use MemoryBroker from brokers.memory."
            )
        self.name = name
        self.broker = broker
        self.potato = potato
        self.schedules: list[schedule.Schedule] = schedules or []
        self._registry: dict[str, Task] = {}
        self._include: list[str] = include or []

    def autodiscover(self) -> None:
        for module_path in self._include:
            importlib.import_module(module_path)

    def task(
        self,
        fn: Callable[..., Coroutine[Any, Any, Any]] | None = None,
        *,
        queue: str = "default",
    ) -> Any:
        def _register(f: Callable[..., Coroutine[Any, Any, Any]]) -> Task:
            task_name = f"{self.name}.{f.__qualname__}"
            t = Task(fn=f, name=task_name, queue=queue, broker=self.broker)
            self._registry[task_name] = t
            return t

        if fn is not None:
            return _register(fn)
        return _register

    def get_task(self, name: str) -> Task:
        try:
            return self._registry[name]
        except KeyError:
            raise KeyError(f"Task '{name}' is not registered in app '{self.name}'.")
