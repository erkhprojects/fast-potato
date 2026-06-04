from __future__ import annotations

import inspect
from collections.abc import AsyncGenerator, Callable
from typing import Any

from core.depends import Depends


class DependencyResolver:
    """
    Resolves Depends() parameters for a callable, recursively.

    - Same dependency callable resolved once per resolver instance (per task execution).
    - Async generators are driven to their yield, then torn down on exit.
    - Use as an async context manager to guarantee teardown.

    Example:
        async with DependencyResolver() as resolver:
            injected = await resolver.resolve(my_task_fn)
            await my_task_fn(**real_args, **injected)
    """

    def __init__(self) -> None:
        self._cache: dict[Callable, Any] = {}
        self._generators: list[AsyncGenerator] = []

    async def resolve(self, fn: Callable) -> dict[str, Any]:
        """Return a dict of {param_name: resolved_value} for every Depends() param of fn."""
        sig = inspect.signature(fn)
        injected: dict[str, Any] = {}

        for name, param in sig.parameters.items():
            if isinstance(param.default, Depends):
                injected[name] = await self._resolve_one(param.default.dependency)

        return injected

    async def _resolve_one(self, dep: Callable) -> Any:
        if dep in self._cache:
            return self._cache[dep]

        # recursively resolve this dependency's own Depends() params first
        sub_kwargs = await self.resolve(dep)

        raw = dep(**sub_kwargs)

        if inspect.isasyncgen(raw):
            value = await raw.__anext__()
            self._generators.append(raw)
        elif inspect.iscoroutine(raw):
            value = await raw
        else:
            value = raw

        self._cache[dep] = value
        return value

    async def _teardown(self) -> None:
        # tear down in reverse order (innermost dependency first)
        for gen in reversed(self._generators):
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass

    async def __aenter__(self) -> DependencyResolver:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self._teardown()
