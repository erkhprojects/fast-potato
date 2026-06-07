from __future__ import annotations

import importlib
from collections.abc import Callable, Coroutine
from typing import Any

from core.protocols import TaskProtocol
from core.schedule import Schedule


class FastPotato:
    def __init__(
        self,
        name: str,
        broker: Any,
        potato: Any = None,
        schedules: list[Schedule] | None = None,
        include: list[str] | None = None,
        cdc: Any = None,
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
        self.schedules: list[Schedule] = schedules or []
        self._registry: dict[str, TaskProtocol] = {}
        self._include: list[str] = include or []
        self._cdc = cdc
        self._cdc_registry: dict[tuple[str, Any], list[Callable]] = {}

    def autodiscover(self) -> None:
        """
        Import every module listed in `include` so their @app.task decorators run
        and tasks register themselves into the registry.

        Called automatically by the worker before starting the consume loop.
        Can also be called manually if needed.

        Example:
            app = FastPotato(
                "my_app",
                broker=RedisBroker(...),
                include=["myapp.orders.tasks", "myapp.emails.tasks"],
            )
            app.autodiscover()  # all tasks now in registry
        """
        for module_path in self._include:
            importlib.import_module(module_path)

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
            return _register(fn)

        return _register

    def get_task(self, name: str) -> TaskProtocol:
        try:
            return self._registry[name]
        except KeyError:
            raise KeyError(f"Task '{name}' is not registered in app '{self.name}'.")

    def on_change(
        self,
        *,
        table: str | None = None,
        collection: str | None = None,
        op: list[str] | None = None,
    ) -> Callable:
        from cdc.base import Operation

        source = table or collection
        if source is None:
            raise ValueError("Provide 'table' (Postgres) or 'collection' (MongoDB)")
        ops = [Operation(o) for o in (op or ["insert", "update", "delete"])]

        def decorator(fn: Callable) -> Callable:
            for operation in ops:
                key = (source, operation)
                self._cdc_registry.setdefault(key, []).append(fn)
            return fn

        return decorator

    async def _dispatch_cdc_event(self, event: Any) -> None:
        key = (event.source, event.op)
        for handler in self._cdc_registry.get(key, []):
            await handler(event)

    async def _run_cdc(self) -> None:
        if self._cdc is None:
            return
        async with self._cdc:
            async for event in self._cdc.stream():
                await self._dispatch_cdc_event(event)
