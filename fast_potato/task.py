from __future__ import annotations

import inspect
import typing
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any, overload

from pydantic import BaseModel
from pydantic_core import PydanticSerializationError

from fast_potato import dependency, message
from fast_potato.brokers import base

DEFAULT_QUEUE = "default"

_SIGNATURE_RULE = (
    "A task takes an optional pydantic BaseModel as its first parameter (the input "
    "sent with .send()); every other parameter must be a dependency: "
    "Depends(...) or Depends[YourPotato]."
)


def _type_hints(fn: Callable[..., Any], task_name: str) -> dict[str, Any]:
    """Evaluate fn's annotations, failing loudly instead of silently skipping them."""
    try:
        return typing.get_type_hints(fn, include_extras=True)
    except Exception as exc:
        raise TypeError(
            f"Task '{task_name}': could not evaluate type annotations ({exc}). "
            "Define the input model and dependency types at module level, "
            "before the task."
        ) from exc


def _inspect_task_signature(
    fn: Callable[..., Any],
    task_name: str,
) -> tuple[type[BaseModel] | None, set[str]]:
    """
    Validate a task function's signature and return (input_model, dependency_params).

    Rules:
      - fn is an ``async def`` function without *args / **kwargs.
      - The first parameter is either a pydantic BaseModel subclass (the input
        model, not a Potato and without a default) or already a dependency.
      - Every remaining parameter is a dependency.
    """
    if not inspect.iscoroutinefunction(fn):
        raise TypeError(f"Task '{task_name}' must be an 'async def' function.")

    params = list(inspect.signature(fn).parameters.values())
    hints = _type_hints(fn, task_name)

    input_model: type[BaseModel] | None = None
    dependency_params: set[str] = set()

    for index, param in enumerate(params):
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            raise TypeError(
                f"Task '{task_name}' must not declare '*{param.name}' or "
                f"'**{param.name}'. {_SIGNATURE_RULE}"
            )

        annotation = hints.get(param.name, param.annotation)
        marker, _ = dependency.extract_dependency(param.default, annotation)
        if marker is not None:
            if param.kind is param.POSITIONAL_ONLY:
                raise TypeError(
                    f"Task '{task_name}' dependency '{param.name}' must not be "
                    "positional-only; dependencies are injected by keyword."
                )
            dependency_params.add(param.name)
            continue

        if index > 0:
            raise TypeError(
                f"Task '{task_name}' parameter '{param.name}' is not a dependency. "
                f"Put task data on the input model instead. {_SIGNATURE_RULE}"
            )

        if annotation is inspect.Parameter.empty:
            raise TypeError(
                f"Task '{task_name}' parameter '{param.name}' is missing a type "
                f"annotation. {_SIGNATURE_RULE}"
            )
        if not (isinstance(annotation, type) and issubclass(annotation, BaseModel)):
            raise TypeError(
                f"Task '{task_name}' input parameter '{param.name}' must be annotated "
                f"with a pydantic BaseModel subclass, got {annotation!r}. "
                f"{_SIGNATURE_RULE}"
            )
        if dependency.is_potato_type(annotation):
            raise TypeError(
                f"Task '{task_name}' input parameter '{param.name}' is a Potato "
                f"({annotation.__name__}). Potatoes are injected, not sent: use "
                f"'{param.name}: {annotation.__name__} = Depends[{annotation.__name__}]'."
            )
        if param.kind is param.KEYWORD_ONLY:
            raise TypeError(
                f"Task '{task_name}' input parameter '{param.name}' must be "
                "positional, not keyword-only."
            )
        if param.default is not inspect.Parameter.empty:
            raise TypeError(
                f"Task '{task_name}' input parameter '{param.name}' must not have "
                "a default value."
            )
        input_model = annotation

    return input_model, dependency_params


class Task[InputT: BaseModel | None, R]:
    """
    A registered task.

    ``InputT`` is the task's input model, or None for tasks that take no input.
    ``send()`` is typed accordingly, so type checkers verify every call.
    """

    def __init__(
        self,
        fn: Callable[..., Coroutine[Any, Any, R]],
        name: str,
        broker: base.AbstractBroker,
        queue: str = DEFAULT_QUEUE,
    ) -> None:
        self._fn: Callable[..., Coroutine[Any, Any, R]] = fn
        self.name = name
        self.queue = queue
        self.broker: base.AbstractBroker = broker
        self._input_model, self._dependency_params = _inspect_task_signature(fn, name)

    @property
    def fn(self) -> Callable[..., Coroutine[Any, Any, R]]:
        """The underlying coroutine function wrapped by this task."""
        return self._fn

    @property
    def input_model(self) -> type[BaseModel] | None:
        """The pydantic model sent as the task's input, or None if it takes none."""
        return self._input_model

    @property
    def dependency_params(self) -> set[str]:
        """Parameter names resolved by dependency injection on the worker."""
        return self._dependency_params

    @overload
    async def send(
        self: Task[None, R],
        *,
        delay: float | None = None,
        eta: datetime | None = None,
        queue: str | None = None,
    ) -> message.TaskMessage: ...

    @overload
    async def send[M: BaseModel](
        self: Task[M, R],
        data: M,
        *,
        delay: float | None = None,
        eta: datetime | None = None,
        queue: str | None = None,
    ) -> message.TaskMessage: ...

    async def send(
        self,
        data: BaseModel | None = None,
        *,
        delay: float | None = None,
        eta: datetime | None = None,
        queue: str | None = None,
    ) -> message.TaskMessage:
        """Publish the task. Pass the input model instance unless the task takes none."""
        msg = self.build_message(data, delay=delay, eta=eta, queue=queue)
        # Lazy connect: producers don't need to connect the broker themselves.
        await self.broker.ensure_connected()
        await self.broker.publish(msg)
        return msg

    def build_message(
        self,
        data: BaseModel | None = None,
        *,
        delay: float | None = None,
        eta: datetime | None = None,
        queue: str | None = None,
    ) -> message.TaskMessage:
        """Validate and serialize the call into a TaskMessage without publishing it."""
        if delay is not None and eta is not None:
            raise ValueError("Provide either 'delay' or 'eta', not both.")

        resolved_eta: datetime | None = eta
        if delay is not None:
            resolved_eta = datetime.now(tz=UTC) + timedelta(seconds=delay)

        return message.TaskMessage(
            task_name=self.name,
            queue=queue if queue is not None else self.queue,
            payload=self._dump_input(data),
            eta=resolved_eta,
        )

    def _dump_input(self, data: BaseModel | None) -> dict[str, Any] | None:
        if self._input_model is None:
            if data is not None:
                raise TypeError(
                    f"Task '{self.name}' takes no input, got {type(data).__name__}."
                )
            return None

        # Exact type only: pydantic dumps a subclass using the declared model's
        # fields, so a subclass's extra fields would be silently dropped.
        if type(data) is not self._input_model:
            raise TypeError(
                f"Task '{self.name}' expects an instance of "
                f"{self._input_model.__name__}, got {type(data).__name__}."
            )
        try:
            return data.model_dump(mode="json")
        except PydanticSerializationError as exc:
            exc.add_note(
                f"Task '{self.name}': every field of {self._input_model.__name__} must "
                "be JSON-serializable by pydantic. For custom types, use "
                "Annotated[T, PlainValidator(...), PlainSerializer(...)] or define "
                "__get_pydantic_core_schema__ on the type."
            )
            raise

    async def __call__(self, *args: Any, **kwargs: Any) -> R:
        """Call the underlying function directly (no serialization or injection)."""
        return await self._fn(*args, **kwargs)
