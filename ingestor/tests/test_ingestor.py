from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import BaseModel

from digester.depends import Depends
from ingestor import FastPotato, TaskMessage


app = FastPotato("test_app")


class Address(BaseModel):
    city: str
    country: str


class User(BaseModel):
    name: str
    age: int
    address: Address


@app.task
async def add(x: int, y: int) -> int:
    return x + y


@app.task
async def greet(user: User) -> str:
    return f"Hello {user.name} from {user.address.city}"


class TestTaskRegistration:
    def test_task_is_registered(self):
        assert "test_app.add" in app._registry

    def test_task_name(self):
        assert add.name == "test_app.add"

    def test_get_task(self):
        assert app.get_task("test_app.add") is add

    def test_get_unknown_task_raises(self):
        with pytest.raises(KeyError, match="not registered"):
            app.get_task("test_app.does_not_exist")


class TestTaskSend:
    async def test_send_returns_task_message(self):
        msg = await add.send(1, 2)
        assert isinstance(msg, TaskMessage)

    async def test_send_stores_args(self):
        msg = await add.send(3, 4)
        assert msg.args == [3, 4]
        assert msg.task_name == "test_app.add"

    async def test_send_with_delay(self):
        msg = await add.send(1, 2, delay=30)
        assert msg.eta is not None

    async def test_send_with_eta(self):
        eta = datetime(2030, 1, 1, tzinfo=timezone.utc)
        msg = await add.send(1, 2, eta=eta)
        assert msg.eta == eta

    async def test_send_delay_and_eta_raises(self):
        with pytest.raises(ValueError, match="not both"):
            await add.send(1, 2, delay=10, eta=datetime(2030, 1, 1, tzinfo=timezone.utc))

    async def test_naive_eta_gets_utc(self):
        msg = await add.send(1, eta=datetime(2030, 6, 1))
        assert msg.eta.tzinfo is not None


class TestPydanticArgSerialization:
    async def test_pydantic_arg_is_serialized(self):
        user = User(name="Alice", age=30, address=Address(city="Berlin", country="DE"))
        msg = await greet.send(user)
        assert isinstance(msg.args[0], dict)
        assert msg.args[0]["__pydantic__"] == "User"

    async def test_nested_model_serialized(self):
        user = User(name="Bob", age=25, address=Address(city="Paris", country="FR"))
        msg = await greet.send(user)
        assert msg.args[0]["data"]["address"]["city"] == "Paris"

    async def test_message_round_trips_json(self):
        user = User(name="Clara", age=28, address=Address(city="Rome", country="IT"))
        msg = await greet.send(user)
        restored = TaskMessage.model_validate_json(msg.model_dump_json())
        assert restored.id == msg.id


class TestTaskDirectCall:
    async def test_task_can_be_called_directly(self):
        result = await add(5, 6)
        assert result == 11


# --- Dependency injection on Task ---

async def get_config() -> dict:
    return {"env": "test"}


@app.task
async def task_with_dep(order_id: int, config: dict = Depends(get_config)) -> str:
    return f"{order_id}:{config['env']}"


class TestTaskDependencyParams:
    def test_dep_params_detected(self):
        assert "config" in task_with_dep.dependency_params

    def test_sendable_params_exclude_deps(self):
        assert "config" not in task_with_dep._sendable_params
        assert "order_id" in task_with_dep._sendable_params

    async def test_send_excludes_dep_from_message(self):
        msg = await task_with_dep.send(order_id=99)
        assert "config" not in msg.kwargs
        assert msg.kwargs.get("order_id") == 99 or msg.args == [99] or msg.kwargs == {"order_id": 99}

    async def test_send_raises_if_dep_param_passed(self):
        with pytest.raises(TypeError, match="resolved automatically"):
            await task_with_dep.send(order_id=1, config={"env": "bad"})
