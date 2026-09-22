from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from fast_potato import (
    BaseTypeStrategy,
    DependencyResolver,
    Depends,
    FastPotato,
    Potato,
    Worker,
)
from fast_potato.brokers import MemoryBroker
from fast_potato.dependency import PotatoDepends
from tests._fixtures import shared_app

# --- Sample Potato subclasses ---


class AppConfig(Potato):
    env: str
    debug: bool = False
    timeout: int = 30


class DatabaseConfig(Potato):
    db_url: str
    pool_size: int = 5


class FullConfig(Potato):
    env: str
    db_url: str
    debug: bool = False


# --- Sample task functions ---


async def task_with_config(
    order_id: int,
    config: AppConfig = Depends[AppConfig],
) -> str:
    return f"{order_id}:{config.env}"


async def task_with_full_config(
    config: FullConfig = Depends[FullConfig],
) -> dict:
    return {"env": config.env, "db": config.db_url}


# --- Potato base model ---


class TestPotatoModel:
    def test_is_pydantic_model(self):
        assert issubclass(Potato, BaseModel)

    def test_frozen_by_default(self):
        config = AppConfig(env="test")
        with pytest.raises(ValidationError):
            config.env = "prod"  # type: ignore[misc]

    def test_subclass_validates_fields(self):
        with pytest.raises(ValidationError):
            AppConfig()  # missing required field 'env'

    def test_subclass_defaults(self):
        config = AppConfig(env="test")
        assert config.debug is False
        assert config.timeout == 30


# --- Depends[X] syntax ---


class TestPotatoDependsSyntax:
    def test_subscript_returns_potato_depends(self):
        marker = Depends[AppConfig]
        assert isinstance(marker, PotatoDepends)

    def test_subscript_stores_type(self):
        marker = Depends[AppConfig]
        assert marker.potato_type is AppConfig

    def test_repr(self):
        assert "AppConfig" in repr(Depends[AppConfig])


# --- FastPotato initialization & type validation ---


class TestFastPotatoInit:
    def test_valid_init(self):
        broker = MemoryBroker()
        config = AppConfig(env="prod")
        app = FastPotato("my_app", broker=broker, potato=config)
        assert app.name == "my_app"
        assert app.broker is broker
        assert app.potato is config
        assert app.schedules == []
        assert app.task_modules == []

    def test_missing_broker_raises_value_error(self):
        with pytest.raises(ValueError, match="requires a broker"):
            FastPotato("test", broker=None)  # type: ignore[arg-type]

    def test_invalid_broker_type_raises_type_error(self):
        with pytest.raises(
            TypeError, match="'broker' must be an instance of AbstractBroker"
        ):
            FastPotato("test", broker="invalid_broker")  # type: ignore[arg-type]

    def test_missing_potato_defaults_to_none(self):
        app = FastPotato("test", broker=MemoryBroker())
        assert app.potato is None

    def test_invalid_potato_type_raises_type_error(self):
        with pytest.raises(TypeError, match="'potato' must be an instance of Potato"):
            FastPotato("test", broker=MemoryBroker(), potato={"env": "prod"})  # type: ignore[arg-type]

    def test_task_modules_stored(self):
        app = FastPotato(
            "test",
            broker=MemoryBroker(),
            task_modules=["tests._fixtures.orders_tasks"],
        )
        assert app.task_modules == ["tests._fixtures.orders_tasks"]

    def test_potato_dep_blocked_from_send(self):
        app = FastPotato("test", broker=MemoryBroker(), potato=AppConfig(env="test"))

        async def my_task(config: AppConfig = Depends[AppConfig]) -> None: ...

        task = app.task(my_task)
        assert "config" in task.dependency_params
        assert "config" not in task._sendable_params


# --- FastPotato task registration ---


class TestFastPotatoTaskRegistration:
    def test_bare_task_decorator(self):
        app = FastPotato("test", broker=MemoryBroker())

        @app.task
        async def sample_task(x: int) -> int:
            return x * 2

        assert (
            "test.TestFastPotatoTaskRegistration.test_bare_task_decorator.<locals>.sample_task"
            in app._registry
        )
        assert app.get_task(sample_task.name) is sample_task

    def test_factory_task_decorator_with_queue(self):
        app = FastPotato("test", broker=MemoryBroker())

        @app.task(queue="priority")
        async def priority_task() -> None:
            pass

        assert priority_task.queue == "priority"
        assert app.get_task(priority_task.name) is priority_task

    def test_get_unknown_task_raises_key_error(self):
        app = FastPotato("test", broker=MemoryBroker())
        with pytest.raises(KeyError, match="not registered"):
            app.get_task("test.nonexistent")


# --- FastPotato autodiscover ---


class TestFastPotatoAutodiscover:
    def test_tasks_not_registered_before_autodiscover(self):
        app = FastPotato(
            "fixture2",
            broker=MemoryBroker(),
            task_modules=["tests._fixtures.orders_tasks"],
        )
        assert len(app._registry) == 0

    def test_autodiscover_registers_tasks_from_module(self):
        shared_app.fixture_app.autodiscover()
        assert any("process_order" in k for k in shared_app.fixture_app._registry)
        assert any("cancel_order" in k for k in shared_app.fixture_app._registry)

    def test_autodiscover_registers_tasks_from_multiple_modules(self):
        shared_app.fixture_app.autodiscover()
        assert any("send_welcome" in k for k in shared_app.fixture_app._registry)

    def test_autodiscover_is_idempotent(self):
        shared_app.fixture_app.autodiscover()
        count_after_first = len(shared_app.fixture_app._registry)
        shared_app.fixture_app.autodiscover()
        assert len(shared_app.fixture_app._registry) == count_after_first

    def test_unknown_module_raises(self):
        app = FastPotato(
            "bad",
            broker=MemoryBroker(),
            task_modules=["myapp.does_not_exist"],
        )
        with pytest.raises(ModuleNotFoundError):
            app.autodiscover()

    def test_empty_task_modules_autodiscover_is_noop(self):
        app = FastPotato("empty", broker=MemoryBroker())
        app.autodiscover()  # should not raise
        assert app._registry == {}


# --- Potato dependency resolution ---


class TestPotatoResolution:
    async def test_resolves_potato_dep(self):
        config = AppConfig(env="staging")
        async with DependencyResolver(potato=config) as r:
            injected = await r.resolve(task_with_config)
        assert injected["config"] is config

    async def test_correct_value_from_potato(self):
        config = AppConfig(env="production", debug=True)
        async with DependencyResolver(potato=config) as r:
            injected = await r.resolve(task_with_config)
        assert injected["config"].env == "production"
        assert injected["config"].debug is True

    async def test_non_dep_param_not_injected(self):
        config = AppConfig(env="test")
        async with DependencyResolver(potato=config) as r:
            injected = await r.resolve(task_with_config)
        assert "order_id" not in injected

    async def test_no_potato_raises_runtime_error(self):
        async with DependencyResolver(potato=None) as r:
            with pytest.raises(RuntimeError, match="no potato was passed"):
                await r.resolve(task_with_config)

    async def test_wrong_potato_type_raises_type_error(self):
        wrong = DatabaseConfig(db_url="postgresql://localhost/db")
        async with DependencyResolver(potato=wrong) as r:
            with pytest.raises(TypeError, match="AppConfig"):
                await r.resolve(task_with_config)

    async def test_potato_dep_mixed_with_callable_dep(self):
        async def get_multiplier() -> int:
            return 10

        async def task_fn(
            config: AppConfig = Depends[AppConfig],
            multiplier: int = Depends(get_multiplier),
        ) -> None: ...

        config = AppConfig(env="test")
        async with DependencyResolver(potato=config) as r:
            injected = await r.resolve(task_fn)

        assert injected["config"].env == "test"
        assert injected["multiplier"] == 10


# --- App-level custom type strategies ---


class Color:
    def __init__(self, r: int, g: int, b: int) -> None:
        self.r = r
        self.g = g
        self.b = b


class ColorStrategy(BaseTypeStrategy):
    def can_handle(self, annotation: Any) -> bool:
        return annotation is Color

    def deserialize(self, val: Any, annotation: Any, dispatcher: Any) -> Any:
        if isinstance(val, dict) and val.get("__color__"):
            return Color(val["r"], val["g"], val["b"])
        return val

    def can_serialize(self, val: Any) -> bool:
        return isinstance(val, Color)

    def serialize(self, val: Any, dispatcher: Any) -> Any:
        return {"__color__": True, "r": val.r, "g": val.g, "b": val.b}


class TestAppTypeStrategy:
    async def test_app_custom_strategy_worker_execution(self):
        broker = MemoryBroker()
        custom_app = FastPotato(
            "color_app",
            broker=broker,
            type_strategies=[ColorStrategy()],
        )

        received_color: list[Color] = []

        @custom_app.task
        async def process_color(c: Color) -> str:
            received_color.append(c)
            return f"rgb({c.r},{c.g},{c.b})"

        msg = await process_color.send(Color(255, 128, 0))
        assert msg.args[0] == {"__color__": True, "r": 255, "g": 128, "b": 0}

        worker = Worker(custom_app)
        result = await worker.execute(msg)
        assert result == "rgb(255,128,0)"
        assert len(received_color) == 1
        assert isinstance(received_color[0], Color)
        assert received_color[0].r == 255

    def test_app_custom_strategy_prioritization(self):
        strat = ColorStrategy()
        app_default = FastPotato("app1", broker=MemoryBroker(), type_strategies=[strat])
        # Default: custom strategies are appended after built-ins
        assert app_default.type_dispatcher.strategies[-1] is strat

        app_prioritized = FastPotato(
            "app2",
            broker=MemoryBroker(),
            type_strategies=[strat],
            prioritize_custom_strategies=True,
        )
        # Prioritized: custom strategies are prepended before built-ins
        assert app_prioritized.type_dispatcher.strategies[0] is strat


# --- Import convention enforcement ---


class TestImportConventions:
    def test_no_submodule_symbol_imports_in_package(self):
        """
        Enforces project convention:
        Never do 'from fast_potato.<submodule> import <Symbol>' inside fast_potato/.
        Always import the module itself: 'from fast_potato import <module>'
        (except in fast_potato/__init__.py for top-level public API exports).
        """
        import ast
        from pathlib import Path

        package_dir = Path(__file__).parent.parent / "fast_potato"
        violations: list[str] = []

        for py_file in package_dir.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
            tree = ast.parse(py_file.read_text("utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    parts = node.module.split(".")
                    if parts[0] == "fast_potato" and len(parts) >= 2:
                        submodule = parts[1]
                        if submodule not in ("brokers",) or len(parts) > 2:
                            symbols = ", ".join(alias.name for alias in node.names)
                            violations.append(
                                f"{py_file.relative_to(package_dir)}:{node.lineno}: "
                                f"from {node.module} import {symbols}"
                            )

        assert not violations, (
            "Forbidden direct submodule imports found! Import the module itself instead:\n"
            + "\n".join(violations)
        )
