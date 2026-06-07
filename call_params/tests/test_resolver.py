from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest

import call_params


# --- Simple fixtures (functions) ---

async def get_value() -> int:
    return 42


async def get_multiplied(val: int = call_params.dependency.Depends(get_value)) -> int:
    return val * 2


# --- Generator fixtures (setup / teardown) ---

teardown_log: list[str] = []


async def get_resource() -> AsyncGenerator[str, None]:
    teardown_log.append("open")
    yield "resource"
    teardown_log.append("close")


async def get_dependent_resource(
    res: str = call_params.dependency.Depends(get_resource),
) -> AsyncGenerator[str, None]:
    teardown_log.append("open_dependent")
    yield f"wrapped({res})"
    teardown_log.append("close_dependent")


# --- Task-like functions ---

async def task_with_deps(
    order_id: int,
    value: int = call_params.dependency.Depends(get_value),
    resource: str = call_params.dependency.Depends(get_resource),
) -> str:
    return f"{order_id}:{value}:{resource}"


async def task_with_nested_deps(
    multiplied: int = call_params.dependency.Depends(get_multiplied),
) -> int:
    return multiplied


class TestResolverBasic:
    async def test_resolves_simple_async_dep(self):
        async with call_params.dependency.DependencyResolver() as r:
            injected = await r.resolve(task_with_deps)
        assert injected["value"] == 42

    async def test_resolves_generator_dep(self):
        async with call_params.dependency.DependencyResolver() as r:
            injected = await r.resolve(task_with_deps)
        assert injected["resource"] == "resource"

    async def test_skips_non_dep_params(self):
        async with call_params.dependency.DependencyResolver() as r:
            injected = await r.resolve(task_with_deps)
        assert "order_id" not in injected

    async def test_nested_dep_resolved(self):
        async with call_params.dependency.DependencyResolver() as r:
            injected = await r.resolve(task_with_nested_deps)
        assert injected["multiplied"] == 84  # 42 * 2


class TestResolverCaching:
    async def test_same_dep_resolved_once(self):
        call_count = 0

        async def counted() -> int:
            nonlocal call_count
            call_count += 1
            return 1

        async def fn_a(x: int = call_params.dependency.Depends(counted)) -> None: ...
        async def fn_b(x: int = call_params.dependency.Depends(counted)) -> None: ...

        async def task_fn(
            a: None = call_params.dependency.Depends(fn_a),
            b: None = call_params.dependency.Depends(fn_b),
        ) -> None: ...

        async with call_params.dependency.DependencyResolver() as r:
            await r.resolve(task_fn)

        # counted() should have been called exactly once despite two paths reaching it
        assert call_count == 1


class TestResolverTeardown:
    async def test_generator_teardown_on_exit(self):
        teardown_log.clear()

        async with call_params.dependency.DependencyResolver() as r:
            await r.resolve(task_with_deps)

        assert "open" in teardown_log
        assert "close" in teardown_log

    async def test_teardown_order_is_reversed(self):
        teardown_log.clear()

        # task that depends on get_dependent_resource, which in turn depends on get_resource
        # teardown should be: close_dependent first, then close (reverse of open order)
        async def task_fn(wrapped: str = call_params.dependency.Depends(get_dependent_resource)) -> None: ...

        async with call_params.dependency.DependencyResolver() as r:
            await r.resolve(task_fn)

        assert teardown_log.index("close_dependent") < teardown_log.index("close")


# ---------------------------------------------------------------------------
# Three-layer dependency chains
#
# Layer 1 (bottom): get_config      — plain async, returns a dict
# Layer 2 (middle): get_service     — depends on get_config, async generator
# Layer 3 (top):    get_handler     — depends on get_service, plain async
# Task:             three_layer_task — depends on get_handler
#
# Also tests a mixed chain where some layers are generators and some are not,
# and verifies values flow correctly through all three levels.
# ---------------------------------------------------------------------------

three_layer_log: list[str] = []


async def get_config() -> dict:
    return {"env": "production", "timeout": 30}


async def get_service(
    config: dict = call_params.dependency.Depends(get_config),
) -> AsyncGenerator[dict, None]:
    three_layer_log.append("service_open")
    yield {"name": "order-service", "env": config["env"]}
    three_layer_log.append("service_close")


async def get_handler(
    service: dict = call_params.dependency.Depends(get_service),
) -> dict:
    return {"handler": "order-handler", "service": service["name"], "env": service["env"]}


async def three_layer_task(
    order_id: int,
    handler: dict = call_params.dependency.Depends(get_handler),
) -> None: ...


class TestThreeLayerDeps:
    async def test_bottom_value_flows_to_top(self):
        async with call_params.dependency.DependencyResolver() as r:
            injected = await r.resolve(three_layer_task)

        handler = injected["handler"]
        assert handler["env"] == "production"          # from get_config (layer 1)
        assert handler["service"] == "order-service"  # from get_service (layer 2)
        assert handler["handler"] == "order-handler"  # from get_handler (layer 3)

    async def test_non_dep_param_not_injected(self):
        async with call_params.dependency.DependencyResolver() as r:
            injected = await r.resolve(three_layer_task)

        assert "order_id" not in injected

    async def test_generator_in_middle_layer_opens(self):
        three_layer_log.clear()

        async with call_params.dependency.DependencyResolver() as r:
            await r.resolve(three_layer_task)

        assert "service_open" in three_layer_log

    async def test_generator_in_middle_layer_closes_on_exit(self):
        three_layer_log.clear()

        async with call_params.dependency.DependencyResolver() as r:
            await r.resolve(three_layer_task)

        assert "service_close" in three_layer_log

    async def test_each_layer_resolved_once(self):
        call_counts: dict[str, int] = {"config": 0, "service": 0, "handler": 0}

        async def counted_config() -> dict:
            call_counts["config"] += 1
            return {"env": "test", "timeout": 5}

        async def counted_service(
            config: dict = call_params.dependency.Depends(counted_config),
        ) -> AsyncGenerator[dict, None]:
            call_counts["service"] += 1
            yield {"name": "svc", "env": config["env"]}

        async def counted_handler(
            service: dict = call_params.dependency.Depends(counted_service),
        ) -> dict:
            call_counts["handler"] += 1
            return {"env": service["env"]}

        async def task_fn(h: dict = call_params.dependency.Depends(counted_handler)) -> None: ...

        async with call_params.dependency.DependencyResolver() as r:
            await r.resolve(task_fn)

        assert call_counts == {"config": 1, "service": 1, "handler": 1}

    async def test_three_layer_all_generators_teardown_in_order(self):
        log: list[str] = []

        async def layer_1() -> AsyncGenerator[str, None]:
            log.append("L1_open")
            yield "L1"
            log.append("L1_close")

        async def layer_2(
            v: str = call_params.dependency.Depends(layer_1),
        ) -> AsyncGenerator[str, None]:
            log.append("L2_open")
            yield f"L2({v})"
            log.append("L2_close")

        async def layer_3(
            v: str = call_params.dependency.Depends(layer_2),
        ) -> AsyncGenerator[str, None]:
            log.append("L3_open")
            yield f"L3({v})"
            log.append("L3_close")

        async def task_fn(v: str = call_params.dependency.Depends(layer_3)) -> None: ...

        async with call_params.dependency.DependencyResolver() as r:
            injected = await r.resolve(task_fn)

        # value threaded through all three layers
        assert injected["v"] == "L3(L2(L1))"

        # opened bottom-up, closed top-down
        assert log.index("L1_open") < log.index("L2_open") < log.index("L3_open")
        assert log.index("L3_close") < log.index("L2_close") < log.index("L1_close")
