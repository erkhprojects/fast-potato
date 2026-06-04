from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from core.protocols import TaskProtocol


class FastPotato:
    def __init__(self, name: str, broker: Any, potato: Any = None) -> None:
        if broker is None:
            raise ValueError(
                "FastPotato requires a broker. "
                "Pass one at init: FastPotato('name', broker=RedisBroker(...)). "
                "For tests and local dev use MemoryBroker from brokers.memory."
            )
        self.name = name
        self.broker = broker
        self.potato = potato
        self._registry: dict[str, TaskProtocol] = {}

    def task(
        self,
        fn: Callable[..., Coroutine[Any, Any, Any]] | None = None,
        *,
        queue: str = "default",
    ) -> Any:
        """
        Register an async function as a task.

        Can be used as a plain decorator or a decorator factory:

            @app.task
            async def simple(): ...

            @app.task(queue="orders")
            async def process_order(): ...
        """
        from core.task import Task

        def _register(f: Callable[..., Coroutine[Any, Any, Any]]) -> TaskProtocol:
            task_name = f"{self.name}.{f.__qualname__}"
            t = Task(fn=f, name=task_name, queue=queue, broker=self.broker)
            self._registry[task_name] = t
            return t

        if fn is not None:
            # used as @app.task — fn is the decorated function
            return _register(fn)

        # used as @app.task(queue="...") — return the decorator
        return _register

    def get_task(self, name: str) -> TaskProtocol:
        try:
            return self._registry[name]
        except KeyError:
            raise KeyError(f"Task '{name}' is not registered in app '{self.name}'.")
