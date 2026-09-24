from __future__ import annotations

import importlib
from collections.abc import Callable, Coroutine
from typing import Any, Concatenate, overload

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
        async def my_task(data: Order, config: AppConfig = Depends[AppConfig]):
            print(config.db_url)

    Frozen by default — config should not change after the app starts.
    Override model_config if you genuinely need mutability.
    """

    model_config = {"frozen": True}


# A task function whose first parameter is of type I (the rest are dependencies).
type _TaskFn[I, R] = Callable[Concatenate[I, ...], Coroutine[Any, Any, R]]
type _AnyTaskFn[R] = Callable[..., Coroutine[Any, Any, R]]


class TaskDecorator:
    """
    Returned by ``app.task(queue=...)``; registers the decorated function.

    Its overloads mirror ``FastPotato.task`` so the parameterized form is typed
    exactly like the bare ``@app.task`` form.
    """

    def __init__(self, app: FastPotato, queue: str) -> None:
        self._app = app
        self._queue = queue

    # A first parameter typed as a Potato is a dependency, so the task takes no
    # input. This overload must precede the BaseModel one (Potato is a BaseModel).
    @overload
    def __call__[P: Potato, R](
        self, fn: _TaskFn[P, R]
    ) -> task_module.Task[None, R]: ...

    @overload
    def __call__[M: BaseModel, R](
        self, fn: _TaskFn[M, R]
    ) -> task_module.Task[M, R]: ...

    @overload
    def __call__[R](self, fn: _AnyTaskFn[R]) -> task_module.Task[None, R]: ...

    def __call__(self, fn: _AnyTaskFn[Any]) -> task_module.Task[Any, Any]:
        return self._app._register(fn, queue=self._queue)


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
        self._broker: base.AbstractBroker = broker
        self.potato: Potato | None = potato
        # Maps a Depends() callable to its replacement, FastAPI-style.
        # Mainly for tests: app.dependency_overrides[get_db] = get_fake_db
        self.dependency_overrides: dict[Callable[..., Any], Callable[..., Any]] = {}
        self.schedules: list[schedule.Schedule] = schedules or []
        self._registry: dict[str, task_module.Task[Any, Any]] = {}
        self.task_modules: list[str] = task_modules or []

    @property
    def broker(self) -> base.AbstractBroker:
        """The message broker configured on this application."""
        return self._broker

    @broker.setter
    def broker(self, new_broker: base.AbstractBroker) -> None:
        if new_broker is None or not isinstance(new_broker, base.AbstractBroker):
            raise TypeError(
                f"'broker' must be an instance of AbstractBroker, got {type(new_broker).__name__}."
            )
        self._broker = new_broker
        for task in self._registry.values():
            task.broker = new_broker

    @property
    def registry(self) -> dict[str, task_module.Task[Any, Any]]:
        """Dictionary of registered tasks mapped by their qualified name."""
        return self._registry

    def autodiscover(self) -> None:
        for module_path in self.task_modules:
            importlib.import_module(module_path)

    @overload
    def task[P: Potato, R](
        self, fn: _TaskFn[P, R], *, queue: str = task_module.DEFAULT_QUEUE
    ) -> task_module.Task[None, R]:
        """``@app.task`` on a function whose first parameter is a Potato dependency."""

    @overload
    def task[M: BaseModel, R](
        self, fn: _TaskFn[M, R], *, queue: str = task_module.DEFAULT_QUEUE
    ) -> task_module.Task[M, R]:
        """``@app.task`` on a function taking an input model: ``send(data: M)``."""

    @overload
    def task[R](
        self, fn: _AnyTaskFn[R], *, queue: str = task_module.DEFAULT_QUEUE
    ) -> task_module.Task[None, R]:
        """``@app.task`` on a function taking no input: ``send()``."""

    @overload
    def task(
        self, fn: None = None, *, queue: str = task_module.DEFAULT_QUEUE
    ) -> TaskDecorator:
        """``@app.task(queue=...)``: returns a decorator that registers the task."""

    def task(
        self,
        fn: _AnyTaskFn[Any] | None = None,
        *,
        queue: str = task_module.DEFAULT_QUEUE,
    ) -> task_module.Task[Any, Any] | TaskDecorator:
        """
        Register an async function as a task on this application.

        The function's first parameter may be a pydantic model: the task's input,
        passed to ``send()``. All other parameters must be dependencies.
        """
        if fn is None:
            return TaskDecorator(self, queue)
        return self._register(fn, queue=queue)

    def _register(
        self, fn: _AnyTaskFn[Any], *, queue: str
    ) -> task_module.Task[Any, Any]:
        task_name = f"{self.name}.{fn.__qualname__}"
        t: task_module.Task[Any, Any] = task_module.Task(
            fn=fn,
            name=task_name,
            broker=self._broker,
            queue=queue,
        )
        self._registry[task_name] = t
        return t

    def get_task(self, name: str) -> task_module.Task[Any, Any]:
        try:
            return self._registry[name]
        except KeyError as exc:
            raise KeyError(
                f"Task '{name}' is not registered in app '{self.name}'."
            ) from exc
