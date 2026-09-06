from __future__ import annotations

import inspect
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel

from fast_potato import dependency, message
from fast_potato.brokers import base


def _serialize_arg(value: Any) -> Any:
    """Recursively serialize an argument to a JSON-safe structure."""
    if isinstance(value, BaseModel):
        return {
            "__pydantic__": type(value).__qualname__,
            "data": value.model_dump(mode="json"),
        }
    if isinstance(value, list):
        return [_serialize_arg(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_arg(v) for k, v in value.items()}
    return value


def _extract_dep_names(fn: Callable) -> set[str]:
    """
    Inspect fn's signature and return the set of dependency parameter names.

    These are parameters declared with Depends() (default-value or Annotated form),
    resolved at execution time by the worker.
    """
    # E.g. for fn(order_id: int, db: Database = Depends(get_db)):
    # sig.parameters -> {"order_id": <Parameter "order_id: int">, "db": <Parameter "db: Database = Depends(...)">}
    sig = inspect.signature(fn)
    hints = dependency.resolved_hints(fn)
    deps: set[str] = set()

    for name, param in sig.parameters.items():
        annotation = hints.get(name, param.annotation)
        dep, _ = dependency.extract_dependency(param.default, annotation)
        if dep is not None:
            deps.add(name)

    return deps


def _validate_send_args(
    sig: inspect.Signature,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    dep_params: set[str],
) -> None:
    """Raise TypeError if any dependency-injected parameter was passed to send() (via args or kwargs)."""
    bound = sig.bind_partial(*args, **kwargs)
    dep_params_passed = dep_params & bound.arguments.keys()
    if dep_params_passed:
        raise TypeError(
            f"Dependency-injected params must not be passed to send(): {dep_params_passed}. "
            "They are resolved automatically by the worker."
        )


DEFAULT_QUEUE = "default"


class Task:
    def __init__(
        self,
        fn: Callable[..., Coroutine[Any, Any, Any]],
        name: str,
        broker: base.AbstractBroker,
        queue: str = DEFAULT_QUEUE,
    ) -> None:
        self._fn = fn
        self.name = name
        self.queue = queue
        self._broker = broker
        self._sig = inspect.signature(fn)
        self.dependency_params = _extract_dep_names(fn)
        self._sendable_params = (
            set(self._sig.parameters.keys()) - self.dependency_params
        )

    async def send(
        self,
        *args: Any,
        delay: float | None = None,
        eta: datetime | None = None,
        queue: str | None = None,
        **kwargs: Any,
    ) -> message.TaskMessage:
        if delay is not None and eta is not None:
            raise ValueError("Provide either 'delay' or 'eta', not both.")

        _validate_send_args(self._sig, args, kwargs, self.dependency_params)

        resolved_eta: datetime | None = eta
        if delay is not None:
            resolved_eta = datetime.now(tz=UTC) + timedelta(seconds=delay)

        msg = message.TaskMessage(
            task_name=self.name,
            queue=queue if queue is not None else self.queue,
            args=[_serialize_arg(a) for a in args],
            kwargs={k: _serialize_arg(v) for k, v in kwargs.items()},
            eta=resolved_eta,
        )

        await self._broker.publish(msg)
        return msg

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return await self._fn(*args, **kwargs)
