from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from typing import Annotated

import pytest

import call_params


# --- dependency providers ---

async def get_value() -> int:
    return 7


def get_sync_value() -> int:
    return 5


teardown_log: list[str] = []


def sync_resource() -> Generator[str, None, None]:
    teardown_log.append("sync_open")
    yield "sync-res"
    teardown_log.append("sync_close")


async def async_resource() -> AsyncGenerator[str, None]:
    teardown_log.append("async_open")
    yield "async-res"
    teardown_log.append("async_close")


class Service:
    """A class dependency whose __init__ itself has a sub-dependency."""

    def __init__(self, value: int = call_params.dependency.Depends(get_value)) -> None:
        self.value = value


# --- task-like functions (module level so type hints resolve) ---

async def task_annotated_func(
    v: Annotated[int, call_params.dependency.Depends(get_value)],
) -> None: ...


async def task_annotated_bare(
    svc: Annotated[Service, call_params.dependency.Depends()],
) -> None: ...


async def task_default_bare(
    svc: Service = call_params.dependency.Depends(),
) -> None: ...


async def task_sync_func(
    n: int = call_params.dependency.Depends(get_sync_value),
) -> None: ...


async def task_sync_gen(
    res: str = call_params.dependency.Depends(sync_resource),
) -> None: ...


async def task_mixed_gens(
    a: str = call_params.dependency.Depends(sync_resource),
    b: str = call_params.dependency.Depends(async_resource),
) -> None: ...


# --- 1. Annotated[T, Depends(...)] ---

class TestAnnotatedForm:
    async def test_annotated_function_dependency(self):
        async with call_params.dependency.DependencyResolver() as r:
            injected = await r.resolve(task_annotated_func)
        assert injected["v"] == 7

    async def test_annotated_leaves_default_slot_free(self):
        # the parameter has no runtime default — the marker lives in the type
        import inspect
        sig = inspect.signature(task_annotated_func)
        assert sig.parameters["v"].default is inspect.Parameter.empty


# --- 2. bare Depends() (infer callable from the annotation) ---

class TestBareDepends:
    async def test_bare_in_annotated_infers_class(self):
        async with call_params.dependency.DependencyResolver() as r:
            injected = await r.resolve(task_annotated_bare)
        assert isinstance(injected["svc"], Service)
        assert injected["svc"].value == 7  # sub-dependency resolved too

    async def test_bare_in_default_form_infers_class(self):
        async with call_params.dependency.DependencyResolver() as r:
            injected = await r.resolve(task_default_bare)
        assert isinstance(injected["svc"], Service)

    async def test_bare_without_type_raises(self):
        async def task(x=call_params.dependency.Depends()) -> None: ...
        async with call_params.dependency.DependencyResolver() as r:
            with pytest.raises(TypeError, match="infer the dependency"):
                await r.resolve(task)


# --- 3. sync functions and sync generators ---

class TestSyncDependencies:
    async def test_sync_function(self):
        async with call_params.dependency.DependencyResolver() as r:
            injected = await r.resolve(task_sync_func)
        assert injected["n"] == 5

    async def test_sync_generator_value_and_teardown(self):
        teardown_log.clear()
        async with call_params.dependency.DependencyResolver() as r:
            injected = await r.resolve(task_sync_gen)
            assert injected["res"] == "sync-res"
            assert "sync_open" in teardown_log
            assert "sync_close" not in teardown_log  # teardown deferred to exit
        assert "sync_close" in teardown_log

    async def test_mixed_sync_and_async_teardown_is_lifo(self):
        teardown_log.clear()
        async with call_params.dependency.DependencyResolver() as r:
            await r.resolve(task_mixed_gens)
        # opened sync then async; torn down in reverse (async first)
        assert teardown_log == ["sync_open", "async_open", "async_close", "sync_close"]


# --- integration: send() ignores Annotated deps ---

class TestSplitParamsWithAnnotated:
    async def test_annotated_dep_excluded_from_send(self):
        import brokers
        import driver

        app = driver.app.FastPotato("t", broker=brokers.memory.MemoryBroker())

        @app.task
        async def my_task(
            order_id: int,
            v: Annotated[int, call_params.dependency.Depends(get_value)],
        ) -> None: ...

        assert "v" in my_task.dependency_params
        assert "v" not in my_task._sendable_params

        msg = await my_task.send(order_id=1)
        assert "v" not in msg.kwargs
