from __future__ import annotations

import pytest

import call_params


# --- Sample Potato subclasses ---

class AppConfig(call_params.potato.Potato):
    env: str
    debug: bool = False
    timeout: int = 30


class DatabaseConfig(call_params.potato.Potato):
    db_url: str
    pool_size: int = 5


class FullConfig(call_params.potato.Potato):
    env: str
    db_url: str
    debug: bool = False


# --- Sample task functions ---

async def task_with_config(
    order_id: int,
    config: AppConfig = call_params.dependency.Depends[AppConfig],
) -> str:
    return f"{order_id}:{config.env}"


async def task_with_full_config(
    config: FullConfig = call_params.dependency.Depends[FullConfig],
) -> dict:
    return {"env": config.env, "db": config.db_url}


# --- Depends[X] syntax ---

class TestPotatoDependsSyntax:
    def test_subscript_returns_potato_depends(self):
        marker = call_params.dependency.Depends[AppConfig]
        assert isinstance(marker, call_params.dependency.PotatoDepends)

    def test_subscript_stores_type(self):
        marker = call_params.dependency.Depends[AppConfig]
        assert marker.potato_type is AppConfig

    def test_repr(self):
        assert "AppConfig" in repr(call_params.dependency.Depends[AppConfig])


# --- Potato base class ---

class TestPotatoModel:
    def test_is_pydantic_model(self):
        from pydantic import BaseModel
        assert issubclass(call_params.potato.Potato, BaseModel)

    def test_frozen_by_default(self):
        config = AppConfig(env="test")
        with pytest.raises(Exception):
            config.env = "prod"  # type: ignore[misc]

    def test_subclass_validates_fields(self):
        with pytest.raises(Exception):
            AppConfig()  # missing required field 'env'

    def test_subclass_defaults(self):
        config = AppConfig(env="test")
        assert config.debug is False
        assert config.timeout == 30


# --- Resolution ---

class TestPotatoResolution:
    async def test_resolves_potato_dep(self):
        config = AppConfig(env="staging")
        async with call_params.dependency.DependencyResolver(potato=config) as r:
            injected = await r.resolve(task_with_config)
        assert injected["config"] is config

    async def test_correct_value_from_potato(self):
        config = AppConfig(env="production", debug=True)
        async with call_params.dependency.DependencyResolver(potato=config) as r:
            injected = await r.resolve(task_with_config)
        assert injected["config"].env == "production"
        assert injected["config"].debug is True

    async def test_non_dep_param_not_injected(self):
        config = AppConfig(env="test")
        async with call_params.dependency.DependencyResolver(potato=config) as r:
            injected = await r.resolve(task_with_config)
        assert "order_id" not in injected

    async def test_no_potato_raises_runtime_error(self):
        async with call_params.dependency.DependencyResolver(potato=None) as r:
            with pytest.raises(RuntimeError, match="no potato was passed"):
                await r.resolve(task_with_config)

    async def test_wrong_potato_type_raises_type_error(self):
        wrong = DatabaseConfig(db_url="postgresql://localhost/db")
        async with call_params.dependency.DependencyResolver(potato=wrong) as r:
            with pytest.raises(TypeError, match="AppConfig"):
                await r.resolve(task_with_config)

    async def test_potato_dep_mixed_with_callable_dep(self):
        async def get_multiplier() -> int:
            return 10

        async def task_fn(
            config: AppConfig = call_params.dependency.Depends[AppConfig],
            multiplier: int = call_params.dependency.Depends(get_multiplier),
        ) -> None: ...

        config = AppConfig(env="test")
        async with call_params.dependency.DependencyResolver(potato=config) as r:
            injected = await r.resolve(task_fn)

        assert injected["config"].env == "test"
        assert injected["multiplier"] == 10


# --- FastPotato app integration ---

class TestFastPotatoAppIntegration:
    def test_app_stores_potato(self):
        import brokers
        import driver
        config = AppConfig(env="prod")
        app = driver.app.FastPotato("test", broker=brokers.memory.MemoryBroker(), potato=config)
        assert app.potato is config

    def test_app_without_potato_defaults_to_none(self):
        import brokers
        import driver
        app = driver.app.FastPotato("test", broker=brokers.memory.MemoryBroker())
        assert app.potato is None

    def test_potato_dep_blocked_from_send(self):
        import brokers
        import driver
        app = driver.app.FastPotato("test", broker=brokers.memory.MemoryBroker(), potato=AppConfig(env="test"))

        async def my_task(config: AppConfig = call_params.dependency.Depends[AppConfig]) -> None: ...

        task = app.task(my_task)
        assert "config" in task.dependency_params
        assert "config" not in task._sendable_params
