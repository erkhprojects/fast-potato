from __future__ import annotations

import inspect
import typing
from collections.abc import AsyncGenerator, Callable, Generator
from typing import Annotated, Any, get_args, get_origin


class _BaseDependency:
    """Marker base for all dependency descriptors used as parameter defaults."""


class Depends(_BaseDependency):
    """
    Declare a callable dependency.

    Three forms are supported:

    1. Explicit callable (function, async function, class, or generator):

        @app.task
        async def my_task(order_id: int, db: Database = Depends(get_db)):
            ...

    2. Annotated form (keeps the parameter's default slot free, recommended):

        @app.task
        async def my_task(db: Annotated[Database, Depends(get_db)]):
            ...

    3. Bare form — the callable is inferred from the type annotation, which
       must itself be callable (typically a class):

        @app.task
        async def my_task(svc: Service = Depends()):              # default form
            ...

        async def my_task(svc: Annotated[Service, Depends()]):    # annotated form
            ...

    For app-level singletons (subclasses of Potato) use the subscript form:

        @app.task
        async def my_task(config: MyConfig = Depends[MyConfig]):
            ...
    """

    def __init__(self, dependency: Callable[..., Any] | None = None) -> None:
        self.dependency = dependency

    def __class_getitem__(cls, potato_type: type) -> PotatoDepends:
        return PotatoDepends(potato_type)

    def __repr__(self) -> str:
        if self.dependency is None:
            return "Depends()"
        return f"Depends({self.dependency.__qualname__})"


class PotatoDepends(_BaseDependency):
    """
    Declare a dependency on the app-level Potato singleton.
    Created via the Depends[SomePotatoSubclass] subscript syntax.
    """

    def __init__(self, potato_type: type) -> None:
        self.potato_type = potato_type

    def __repr__(self) -> str:
        return f"Depends[{self.potato_type.__name__}]"


def _resolved_hints(fn: Callable) -> dict[str, Any]:
    """
    Resolved type hints for fn (with Annotated metadata preserved), or {} when
    they cannot be evaluated.

    Using get_type_hints means string annotations produced by
    ``from __future__ import annotations`` are resolved back to real objects, so
    the ``Annotated[T, Depends(...)]`` marker is visible. For a class, the hints
    of its ``__init__`` are returned, matching ``inspect.signature(cls)``.
    """
    target = fn.__init__ if inspect.isclass(fn) else fn
    try:
        return typing.get_type_hints(target, include_extras=True)
    except Exception:
        return {}


def _param_dependency(
    param: inspect.Parameter, hints: dict[str, Any]
) -> tuple[_BaseDependency | None, Any]:
    """
    Inspect one parameter and return ``(marker, base_type)``.

    ``marker`` is the dependency descriptor for the parameter — sourced from the
    default-value form ``x: T = Depends(...)`` or the ``Annotated[T, Depends(...)]``
    form — or None when the parameter is not a dependency. ``base_type`` is the
    underlying type T, used to infer the callable for a bare ``Depends()``.
    """
    annotation = hints.get(param.name, param.annotation)

    # Annotated[T, Depends(...)] form
    if get_origin(annotation) is Annotated:
        args = get_args(annotation)
        for meta in args[1:]:
            if isinstance(meta, _BaseDependency):
                return meta, args[0]

    # x: T = Depends(...) default-value form
    if isinstance(param.default, _BaseDependency):
        base_type = annotation
        if get_origin(base_type) is Annotated:
            base_type = get_args(base_type)[0]
        if isinstance(base_type, str) or base_type is inspect.Parameter.empty:
            base_type = None
        return param.default, base_type

    return None, None


class DependencyResolver:
    """
    Resolves Depends() and Depends[Potato] parameters for a callable, recursively.

    - Same dependency callable resolved once per resolver instance (per task execution).
    - Dependencies may be async functions, plain sync functions, classes, or
      async/sync generators. Generators are driven to their first yield, then
      torn down (in reverse resolution order) on exit.
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
        # (kind, generator) pairs in resolution order; kind is "sync" or "async"
        self._generators: list[tuple[str, Generator | AsyncGenerator]] = []

    async def resolve(self, fn: Callable) -> dict[str, Any]:
        """Return {param_name: resolved_value} for every dependency param of fn."""
        sig = inspect.signature(fn)
        hints = _resolved_hints(fn)
        injected: dict[str, Any] = {}

        for name, param in sig.parameters.items():
            marker, base_type = _param_dependency(param, hints)
            if marker is None:
                continue
            if isinstance(marker, PotatoDepends):
                injected[name] = self._resolve_potato(marker)
            else:  # Depends
                dep = marker.dependency
                if dep is None:  # bare Depends() — infer the callable from the type
                    dep = base_type
                if dep is None or not callable(dep):
                    raise TypeError(
                        f"Bare Depends() on parameter {name!r} needs a callable type "
                        "annotation to infer the dependency, e.g. "
                        "`x: MyClass = Depends()` or `x: Annotated[MyClass, Depends()]`."
                    )
                injected[name] = await self._resolve_one(dep)

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
            self._generators.append(("async", raw))
        elif inspect.isgenerator(raw):
            value = next(raw)
            self._generators.append(("sync", raw))
        elif inspect.iscoroutine(raw):
            value = await raw
        else:
            value = raw

        self._cache[dep] = value
        return value

    async def _teardown(self) -> None:
        for kind, gen in reversed(self._generators):
            if kind == "async":
                try:
                    await gen.__anext__()
                except StopAsyncIteration:
                    pass
            else:
                try:
                    next(gen)
                except StopIteration:
                    pass

    async def __aenter__(self) -> DependencyResolver:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self._teardown()
