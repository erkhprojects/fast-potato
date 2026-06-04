from __future__ import annotations

import pytest

from core.depends import Depends, PotatoDepends
from core.potato import Potato
from core.resolver import DependencyResolver


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


# --- Potato base class ---

class TestPotatoModel:
    def test_is_pydantic_model(self):
        from pydantic import BaseModel
        assert issubclass(Potato, BaseModel)

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


# --- FastPotato app integration ---

class TestFastPotatoAppIntegration:
    def test_app_stores_potato(self):
        from core.app import FastPotato
        config = AppConfig(env="prod")
        app = FastPotato("test", potato=config)
        assert app.potato is config

    def test_app_without_potato_defaults_to_none(self):
        from core.app import FastPotato
        app = FastPotato("test")
        assert app.potato is None

    def test_potato_dep_blocked_from_send(self):
        from core.app import FastPotato
        app = FastPotato("test", potato=AppConfig(env="test"))

        async def my_task(config: AppConfig = Depends[AppConfig]) -> None: ...

        task = app.task(my_task)
        assert "config" in task.dependency_params
        assert "config" not in task._sendable_params
