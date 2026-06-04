from __future__ import annotations

import inspect
from collections.abc import AsyncGenerator, Callable
from typing import Any

from core.depends import Depends, PotatoDepends


class DependencyResolver:
    """
    Resolves Depends() and Depends[Potato] parameters for a callable, recursively.

    - Same dependency callable resolved once per resolver instance (per task execution).
    - Async generators are driven to their yield, then torn down on exit.
    - Depends[PotatoSubclass] resolves to the app-level potato singleton.
    - Use as an async context manager to guarantee teardown.

    Example:
        async with DependencyResolver(potato=app.potato) as resolver:
            injected = await resolver.resolve(my_task_fn)
            await my_task_fn(**real_args, **injected)
    """

    def __init__(self, potato: Any = None) -> None:
        self._potato = potato
        self._cache: dict[Callable, Any] = {}
        self._generators: list[AsyncGenerator] = []

    async def resolve(self, fn: Callable) -> dict[str, Any]:
        """Return {param_name: resolved_value} for every dependency param of fn."""
        sig = inspect.signature(fn)
        injected: dict[str, Any] = {}

        for name, param in sig.parameters.items():
            if isinstance(param.default, PotatoDepends):
                injected[name] = self._resolve_potato(param.default)
            elif isinstance(param.default, Depends):
                injected[name] = await self._resolve_one(param.default.dependency)

        return injected

    def _resolve_potato(self, dep: PotatoDepends) -> Any:
        if self._potato is None:
            raise RuntimeError(
                f"Task depends on {dep!r} but no potato was passed to FastPotato(). "
                "Initialize the app with FastPotato('name', potato=YourConfig(...))."
            )
        if not isinstance(self._potato, dep.potato_type):
            raise TypeError(
                f"App potato is {type(self._potato).__name__!r}, "
                f"but task expected {dep.potato_type.__name__!r}."
            )
        return self._potato

    async def _resolve_one(self, dep: Callable) -> Any:
        if dep in self._cache:
            return self._cache[dep]

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
        for gen in reversed(self._generators):
            try:
                await gen.__anext__()
            except StopAsyncIteration:
                pass

    async def __aenter__(self) -> DependencyResolver:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self._teardown()
