from __future__ import annotations

import inspect
from collections.abc import AsyncGenerator, Generator
from typing import Annotated

import pytest

from fast_potato import DependencyResolver, Depends, FastPotato, extract_dependency
from fast_potato.brokers import MemoryBroker
from fast_potato.dependency import _BaseDependency

# --- Simple fixtures (functions) ---


async def get_value() -> int:
    return 42


async def get_multiplied(val: int = Depends(get_value)) -> int:
    return val * 2


def get_sync_value() -> int:
    return 5


# --- Generator fixtures (setup / teardown) ---

teardown_log: list[str] = []


async def get_resource() -> AsyncGenerator[str]:
    teardown_log.append("open")
    yield "resource"
    teardown_log.append("close")


async def get_dependent_resource(
    res: str = Depends(get_resource),
) -> AsyncGenerator[str]:
    teardown_log.append("open_dependent")
    yield f"wrapped({res})"
    teardown_log.append("close_dependent")


def sync_resource() -> Generator[str]:
    teardown_log.append("sync_open")
    yield "sync-res"
    teardown_log.append("sync_close")


async def async_resource() -> AsyncGenerator[str]:
    teardown_log.append("async_open")
    yield "async-res"
    teardown_log.append("async_close")


class Service:
    """A class dependency whose __init__ itself has a sub-dependency."""

    def __init__(self, value: int = Depends(get_value)) -> None:
        self.value = value


# --- Task-like functions ---


async def task_with_deps(
    order_id: int,
    value: int = Depends(get_value),
    resource: str = Depends(get_resource),
) -> str:
    return f"{order_id}:{value}:{resource}"


async def task_with_nested_deps(
    multiplied: int = Depends(get_multiplied),
) -> int:
    return multiplied


async def task_annotated_func(
    v: Annotated[int, Depends(get_value)],
) -> None: ...


async def task_annotated_bare(
    svc: Annotated[Service, Depends()],
) -> None: ...


async def task_default_bare(
    svc: Service = Depends(),
) -> None: ...


async def task_sync_func(
    n: int = Depends(get_sync_value),
) -> None: ...


async def task_sync_gen(
    res: str = Depends(sync_resource),
) -> None: ...


async def task_mixed_gens(
    a: str = Depends(sync_resource),
    b: str = Depends(async_resource),
) -> None: ...


# --- 1. Basic Resolver Tests ---


class TestResolverBasic:
    async def test_resolves_simple_async_dep(self):
        async with DependencyResolver() as r:
            injected = await r.resolve(task_with_deps)
        assert injected["value"] == 42

    async def test_resolves_generator_dep(self):
        async with DependencyResolver() as r:
            injected = await r.resolve(task_with_deps)
        assert injected["resource"] == "resource"

    async def test_skips_non_dep_params(self):
        async with DependencyResolver() as r:
            injected = await r.resolve(task_with_deps)
        assert "order_id" not in injected

    async def test_nested_dep_resolved(self):
        async with DependencyResolver() as r:
            injected = await r.resolve(task_with_nested_deps)
        assert injected["multiplied"] == 84  # 42 * 2


# --- 2. Caching & Single Execution ---


class TestResolverCaching:
    async def test_same_dep_resolved_once(self):
        call_count = 0

        async def counted() -> int:
            nonlocal call_count
            call_count += 1
            return 1

        async def fn_a(x: int = Depends(counted)) -> None: ...
        async def fn_b(x: int = Depends(counted)) -> None: ...

        async def task_fn(
            a: None = Depends(fn_a),
            b: None = Depends(fn_b),
        ) -> None: ...

        async with DependencyResolver() as r:
            await r.resolve(task_fn)

        assert call_count == 1


# --- 3. Teardown Lifecycle ---


class TestResolverTeardown:
    async def test_generator_teardown_on_exit(self):
        teardown_log.clear()

        async with DependencyResolver() as r:
            await r.resolve(task_with_deps)

        assert "open" in teardown_log
        assert "close" in teardown_log

    async def test_teardown_order_is_reversed(self):
        teardown_log.clear()

        async def task_fn(wrapped: str = Depends(get_dependent_resource)) -> None: ...

        async with DependencyResolver() as r:
            await r.resolve(task_fn)

        assert teardown_log.index("close_dependent") < teardown_log.index("close")


# --- 4. Multi-layer Dependency Chains ---

three_layer_log: list[str] = []


async def get_config() -> dict:
    return {"env": "production", "timeout": 30}


async def get_service(
    config: dict = Depends(get_config),
) -> AsyncGenerator[dict]:
    three_layer_log.append("service_open")
    yield {"name": "order-service", "env": config["env"]}
    three_layer_log.append("service_close")


async def get_handler(
    service: dict = Depends(get_service),
) -> dict:
    return {
        "handler": "order-handler",
        "service": service["name"],
        "env": service["env"],
    }


async def three_layer_task(
    order_id: int,
    handler: dict = Depends(get_handler),
) -> None: ...


class TestThreeLayerDeps:
    async def test_bottom_value_flows_to_top(self):
        async with DependencyResolver() as r:
            injected = await r.resolve(three_layer_task)

        handler = injected["handler"]
        assert handler["env"] == "production"
        assert handler["service"] == "order-service"
        assert handler["handler"] == "order-handler"

    async def test_non_dep_param_not_injected(self):
        async with DependencyResolver() as r:
            injected = await r.resolve(three_layer_task)

        assert "order_id" not in injected

    async def test_generator_in_middle_layer_opens(self):
        three_layer_log.clear()

        async with DependencyResolver() as r:
            await r.resolve(three_layer_task)

        assert "service_open" in three_layer_log

    async def test_generator_in_middle_layer_closes_on_exit(self):
        three_layer_log.clear()

        async with DependencyResolver() as r:
            await r.resolve(three_layer_task)

        assert "service_close" in three_layer_log

    async def test_each_layer_resolved_once(self):
        call_counts: dict[str, int] = {"config": 0, "service": 0, "handler": 0}

        async def counted_config() -> dict:
            call_counts["config"] += 1
            return {"env": "test", "timeout": 5}

        async def counted_service(
            config: dict = Depends(counted_config),
        ) -> AsyncGenerator[dict]:
            call_counts["service"] += 1
            yield {"name": "svc", "env": config["env"]}

        async def counted_handler(
            service: dict = Depends(counted_service),
        ) -> dict:
            call_counts["handler"] += 1
            return {"env": service["env"]}

        async def task_fn(h: dict = Depends(counted_handler)) -> None: ...

        async with DependencyResolver() as r:
            await r.resolve(task_fn)

        assert call_counts == {"config": 1, "service": 1, "handler": 1}

    async def test_three_layer_all_generators_teardown_in_order(self):
        log: list[str] = []

        async def layer_1() -> AsyncGenerator[str]:
            log.append("L1_open")
            yield "L1"
            log.append("L1_close")

        async def layer_2(
            v: str = Depends(layer_1),
        ) -> AsyncGenerator[str]:
            log.append("L2_open")
            yield f"L2({v})"
            log.append("L2_close")

        async def layer_3(
            v: str = Depends(layer_2),
        ) -> AsyncGenerator[str]:
            log.append("L3_open")
            yield f"L3({v})"
            log.append("L3_close")

        async def task_fn(v: str = Depends(layer_3)) -> None: ...

        async with DependencyResolver() as r:
            injected = await r.resolve(task_fn)

        assert injected["v"] == "L3(L2(L1))"
        assert log.index("L1_open") < log.index("L2_open") < log.index("L3_open")
        assert log.index("L3_close") < log.index("L2_close") < log.index("L1_close")

    async def test_unsupported_dependency_marker_raises(self):
        class UnknownDep(_BaseDependency):
            pass

        async def task_fn(v: str = UnknownDep()) -> None: ...

        async with DependencyResolver() as r:
            with pytest.raises(TypeError, match="Unsupported dependency marker"):
                await r.resolve(task_fn)

    async def test_resolve_params_and_call_provider_methods(self):
        async with DependencyResolver() as r:
            injected = await r.resolve_params(task_with_deps)
            assert injected["value"] == 42
            assert injected["resource"] == "resource"

            val = await r._call_provider(get_value)
            assert val == 42


# --- 5. Annotated[T, Depends(...)] Form ---


class TestAnnotatedForm:
    async def test_annotated_function_dependency(self):
        async with DependencyResolver() as r:
            injected = await r.resolve(task_annotated_func)
        assert injected["v"] == 42

    async def test_annotated_leaves_default_slot_free(self):
        sig = inspect.signature(task_annotated_func)
        assert sig.parameters["v"].default is inspect.Parameter.empty


# --- 6. Bare Depends() (Infer callable from annotation) ---


class TestBareDepends:
    async def test_bare_in_annotated_infers_class(self):
        async with DependencyResolver() as r:
            injected = await r.resolve(task_annotated_bare)
        assert isinstance(injected["svc"], Service)
        assert injected["svc"].value == 42

    async def test_bare_in_default_form_infers_class(self):
        async with DependencyResolver() as r:
            injected = await r.resolve(task_default_bare)
        assert isinstance(injected["svc"], Service)

    async def test_bare_without_type_raises(self):
        async def task(x=Depends()) -> None: ...

        async with DependencyResolver() as r:
            with pytest.raises(TypeError, match="infer the dependency"):
                await r.resolve(task)


# --- 7. Sync Functions & Sync Generators ---


class TestSyncDependencies:
    async def test_sync_function(self):
        async with DependencyResolver() as r:
            injected = await r.resolve(task_sync_func)
        assert injected["n"] == 5

    async def test_sync_generator_value_and_teardown(self):
        teardown_log.clear()
        async with DependencyResolver() as r:
            injected = await r.resolve(task_sync_gen)
            assert injected["res"] == "sync-res"
            assert "sync_open" in teardown_log
            assert "sync_close" not in teardown_log
        assert "sync_close" in teardown_log

    async def test_mixed_sync_and_async_teardown_is_lifo(self):
        teardown_log.clear()
        async with DependencyResolver() as r:
            await r.resolve(task_mixed_gens)
        assert teardown_log == ["sync_open", "async_open", "async_close", "sync_close"]


# --- 8. Integration: send() ignores Annotated deps ---


class TestSplitParamsWithAnnotated:
    async def test_annotated_dep_excluded_from_send(self):
        app = FastPotato("t", broker=MemoryBroker())

        @app.task
        async def my_task(
            order_id: int,
            v: Annotated[int, Depends(get_value)],
        ) -> None: ...

        assert "v" in my_task.dependency_params
        assert "v" not in my_task._sendable_params

        msg = await my_task.send(order_id=1)
        assert "v" not in msg.kwargs


# --- 9. extract_dependency Helper ---


class TestExtractDependency:
    def test_default_dependency(self):
        dep = Depends(get_value)
        marker, base_type = extract_dependency(default=dep, annotation=int)
        assert marker is dep
        assert base_type is int

    def test_annotated_dependency(self):
        dep = Depends(get_value)
        marker, base_type = extract_dependency(annotation=Annotated[int, dep])
        assert marker is dep
        assert base_type is int

    def test_annotated_bare_dependency(self):
        dep = Depends()
        marker, base_type = extract_dependency(annotation=Annotated[Service, dep])
        assert marker is dep
        assert base_type is Service

    def test_non_dependency(self):
        marker, base_type = extract_dependency(default=42, annotation=int)
        assert marker is None
        assert base_type is None
