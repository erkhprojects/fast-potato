from __future__ import annotations

import importlib
from collections.abc import Callable, Coroutine
from typing import Any, overload

from pydantic import BaseModel

from fast_potato import schedule
from fast_potato import task as task_module
from fast_potato.brokers import base


class Potato(BaseModel):
    """
    Base class for app-level singleton dependencies.

    Subclass this to define shared config or resources that are initialized
    once when the app starts and injected into tasks via Depends[YourClass].

    Example:
        class AppConfig(Potato):
            db_url: str
            redis_url: str
            debug: bool = False

        app = FastPotato("my_app", potato=AppConfig(db_url="...", redis_url="..."))

        @app.task
        async def my_task(order_id: int, config: AppConfig = Depends[AppConfig]):
            print(config.db_url)

    Frozen by default — config should not change after the app starts.
    Override model_config if you genuinely need mutability.
    """

    model_config = {"frozen": True}


class FastPotato:
    def __init__(
        self,
        name: str,
        broker: base.AbstractBroker,
        potato: Potato | None = None,
        schedules: list[schedule.Schedule] | None = None,
        task_modules: list[str] | None = None,
    ) -> None:
        if broker is None:
            raise ValueError(
                "FastPotato requires a broker. "
                "Pass one at init: FastPotato('name', broker=RedisBroker(...)). "
                "For tests and local dev use MemoryBroker from brokers.memory."
            )
        if not isinstance(broker, base.AbstractBroker):
            raise TypeError(
                f"'broker' must be an instance of AbstractBroker, got {type(broker).__name__}."
            )
        if potato is not None and not isinstance(potato, Potato):
            raise TypeError(
                f"'potato' must be an instance of Potato, got {type(potato).__name__}."
            )
        self.name = name
        self.broker: base.AbstractBroker = broker
        self.potato: Potato | None = potato
        self.schedules: list[schedule.Schedule] = schedules or []
        self._registry: dict[str, task_module.Task] = {}
        self.task_modules: list[str] = task_modules or []

    @property
    def registry(self) -> dict[str, task_module.Task]:
        """Dictionary of registered tasks mapped by their qualified name."""
        return self._registry

    def autodiscover(self) -> None:
        for module_path in self.task_modules:
            importlib.import_module(module_path)

    @overload
    def task(
        self,
        fn: Callable[..., Coroutine[Any, Any, Any]],
        *,
        queue: str = "default",
    ) -> task_module.Task:
        """Bare decorator (e.g. ``@app.task``): directly registers the coroutine as a Task."""

    @overload
    def task(
        self,
        fn: None = None,
        *,
        queue: str = "default",
    ) -> Callable[[Callable[..., Coroutine[Any, Any, Any]]], task_module.Task]:
        """Parameterized decorator (e.g. ``@app.task(queue='urgent')``): returns a decorator to register the Task."""

    def task(
        self,
        fn: Callable[..., Coroutine[Any, Any, Any]] | None = None,
        *,
        queue: str = "default",
    ) -> Any:
        """Register an async function as a task on this application."""

        def _register(f: Callable[..., Coroutine[Any, Any, Any]]) -> task_module.Task:
            task_name = f"{self.name}.{f.__qualname__}"
            t = task_module.Task(fn=f, name=task_name, queue=queue, broker=self.broker)
            self._registry[task_name] = t
            return t

        if fn is not None:
            return _register(fn)
        return _register

    def get_task(self, name: str) -> task_module.Task:
        try:
            return self._registry[name]
        except KeyError as exc:
            raise KeyError(
                f"Task '{name}' is not registered in app '{self.name}'."
            ) from exc
