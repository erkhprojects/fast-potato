from __future__ import annotations

import importlib
from collections.abc import Callable, Coroutine
from typing import Any

from pydantic import BaseModel

from fast_potato import schedule, task


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
        self._registry: dict[str, task.Task] = {}
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
        def _register(f: Callable[..., Coroutine[Any, Any, Any]]) -> task.Task:
            task_name = f"{self.name}.{f.__qualname__}"
            t = task.Task(fn=f, name=task_name, queue=queue, broker=self.broker)
            self._registry[task_name] = t
            return t

        if fn is not None:
            return _register(fn)
        return _register

    def get_task(self, name: str) -> task.Task:
        try:
            return self._registry[name]
        except KeyError:
            raise KeyError(f"Task '{name}' is not registered in app '{self.name}'.")
