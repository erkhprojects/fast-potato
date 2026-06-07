from __future__ import annotations

import inspect
from collections.abc import Callable, Coroutine
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel

from brokers import base
from call_params import dependency, message


def _serialize_arg(value: Any) -> Any:
    """Recursively serialize an argument to a JSON-safe structure."""
    if isinstance(value, BaseModel):
        return {"__pydantic__": type(value).__qualname__, "data": value.model_dump(mode="json")}
    if isinstance(value, list):
        return [_serialize_arg(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize_arg(v) for k, v in value.items()}
    return value


def _split_params(fn: Callable) -> tuple[set[str], set[str]]:
    """
    Inspect fn's signature and return (sendable_params, dependency_params).

    sendable_params  — regular params the caller must/can pass via send()
    dependency_params — params declared with Depends() (default-value or Annotated
                        form), resolved at execution time
    """
    sig = inspect.signature(fn)
    hints = dependency._resolved_hints(fn)
    sendable: set[str] = set()
    deps: set[str] = set()

    for name, param in sig.parameters.items():
        marker, _ = dependency._param_dependency(param, hints)
        if marker is not None:
            deps.add(name)
        else:
            sendable.add(name)

    return sendable, deps


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
        self._sendable_params, self.dependency_params = _split_params(fn)

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

        dep_params_passed = self.dependency_params & kwargs.keys()
        if dep_params_passed:
            raise TypeError(
                f"Dependency-injected params must not be passed to send(): {dep_params_passed}. "
                "They are resolved automatically by the worker."
            )

        resolved_eta: datetime | None = eta
        if delay is not None:
            resolved_eta = datetime.now(tz=timezone.utc) + timedelta(seconds=delay)

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
