from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

import pytest
from pydantic import BaseModel

from fast_potato import Depends, FastPotato, Potato, TaskMessage
from fast_potato.brokers import MemoryBroker

app = FastPotato("test_app", broker=MemoryBroker())


class Address(BaseModel):
    city: str
    country: str


class User(BaseModel):
    name: str
    age: int
    address: Address


class VipUser(User):
    tier: str


class AddInput(BaseModel):
    x: int
    y: int


class AppConfig(Potato):
    env: str = "test"


async def get_config() -> dict:
    return {"env": "test"}


@app.task
async def add(data: AddInput) -> int:
    return data.x + data.y


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

    def test_input_model_detected(self):
        assert add.input_model is AddInput
        assert add.dependency_params == set()


class TestSignatureRules:
    def test_untyped_input_parameter_raises(self):
        with pytest.raises(TypeError, match="missing a type annotation"):

            @app.task
            async def untyped_param(x):  # type: ignore[no-untyped-def]
                pass

    def test_primitive_input_raises(self):
        with pytest.raises(TypeError, match="pydantic BaseModel subclass"):

            @app.task
            async def primitive(x: int) -> None: ...

    def test_optional_model_input_raises(self):
        with pytest.raises(TypeError, match="pydantic BaseModel subclass"):

            @app.task
            async def optional(user: User | None) -> None: ...

    def test_second_non_dependency_parameter_raises(self):
        with pytest.raises(TypeError, match="'extra' is not a dependency"):

            @app.task
            async def two_inputs(user: User, extra: int) -> None: ...

    def test_potato_input_raises(self):
        with pytest.raises(TypeError, match="Potatoes are injected"):

            @app.task
            async def potato_input(config: AppConfig) -> None: ...

    def test_input_with_default_raises(self):
        with pytest.raises(TypeError, match="must not have a default"):

            @app.task
            async def defaulted(
                data: AddInput = AddInput(x=1, y=2),  # noqa: B008
            ) -> None: ...

    def test_keyword_only_input_raises(self):
        with pytest.raises(TypeError, match="not keyword-only"):

            @app.task
            async def kw_only(*, data: AddInput) -> None: ...

    def test_var_args_raise(self):
        with pytest.raises(TypeError, match=r"must not declare '\*args'"):

            @app.task
            async def var_args(*args: int) -> None: ...

    def test_sync_function_raises(self):
        with pytest.raises(TypeError, match="async def"):
            app.task(lambda: None)  # type: ignore[call-overload]

    def test_unresolvable_annotation_raises(self):
        with pytest.raises(TypeError, match="could not evaluate type annotations"):

            @app.task
            async def unresolvable(data: DoesNotExist) -> None: ...  # type: ignore[name-defined]  # noqa: F821


class TestTaskSend:
    async def test_send_returns_task_message(self):
        msg = await add.send(AddInput(x=1, y=2))
        assert isinstance(msg, TaskMessage)

    async def test_send_stores_payload(self):
        msg = await add.send(AddInput(x=3, y=4))
        assert msg.payload == {"x": 3, "y": 4}
        assert msg.task_name == "test_app.add"

    async def test_send_with_delay(self):
        msg = await add.send(AddInput(x=1, y=2), delay=30)
        assert msg.eta is not None

    async def test_send_with_eta(self):
        eta = datetime(2030, 1, 1, tzinfo=UTC)
        msg = await add.send(AddInput(x=1, y=2), eta=eta)
        assert msg.eta == eta

    async def test_send_delay_and_eta_raises(self):
        with pytest.raises(ValueError, match="not both"):
            await add.send(
                AddInput(x=1, y=2), delay=10, eta=datetime(2030, 1, 1, tzinfo=UTC)
            )

    async def test_naive_eta_gets_utc(self):
        msg = await add.send(AddInput(x=1, y=2), eta=datetime(2030, 6, 1))
        assert msg.eta is not None
        assert msg.eta.tzinfo is not None

    async def test_send_without_input_raises(self):
        with pytest.raises(TypeError, match="expects an instance of AddInput"):
            await add.send()  # type: ignore[call-overload]

    async def test_send_dict_raises(self):
        with pytest.raises(TypeError, match="got dict"):
            await add.send({"x": 1, "y": 2})  # type: ignore[call-overload]

    async def test_send_subclass_raises(self):
        vip = VipUser(
            name="A", age=1, address=Address(city="B", country="C"), tier="gold"
        )
        with pytest.raises(TypeError, match="got VipUser"):
            await greet.send(vip)

    async def test_send_input_to_no_input_task_raises(self):
        with pytest.raises(TypeError, match="takes no input"):
            await default_queue_task.send(AddInput(x=1, y=2))  # type: ignore[call-overload]


class TestPydanticSerialization:
    async def test_nested_model_serialized_by_pydantic(self):
        user = User(name="Bob", age=25, address=Address(city="Paris", country="FR"))
        msg = await greet.send(user)
        assert msg.payload == {
            "name": "Bob",
            "age": 25,
            "address": {"city": "Paris", "country": "FR"},
        }

    async def test_message_round_trips_json(self):
        user = User(name="Clara", age=28, address=Address(city="Rome", country="IT"))
        msg = await greet.send(user)
        restored = TaskMessage.model_validate_json(msg.model_dump_json())
        assert restored == msg
        assert User.model_validate(restored.payload) == user


class TestTaskDirectCall:
    async def test_task_can_be_called_directly(self):
        result = await add(AddInput(x=5, y=6))
        assert result == 11


# --- Dependency injection on Task ---


@app.task
async def task_with_dep(data: AddInput, config: dict = Depends(get_config)) -> str:
    return f"{data.x}:{config['env']}"


@app.task
async def annotated_dep_only(config: Annotated[dict, Depends(get_config)]) -> None: ...


@app.task
async def potato_dep_only(config: AppConfig = Depends[AppConfig]) -> None: ...


class TestTaskDependencyParams:
    def test_dep_params_detected(self):
        assert task_with_dep.dependency_params == {"config"}
        assert task_with_dep.input_model is AddInput

    def test_dependency_only_tasks_take_no_input(self):
        assert annotated_dep_only.input_model is None
        assert annotated_dep_only.dependency_params == {"config"}
        assert potato_dep_only.input_model is None

    async def test_send_excludes_dep_from_message(self):
        msg = await task_with_dep.send(AddInput(x=99, y=0))
        assert msg.payload == {"x": 99, "y": 0}

    async def test_no_input_task_has_no_payload(self):
        msg = await annotated_dep_only.send()
        assert msg.payload is None


# --- Queue annotation ---


@app.task
async def default_queue_task() -> None: ...


@app.task(queue="orders")
async def orders_task() -> None: ...


@app.task(queue="emails")
async def emails_task() -> None: ...


class TestQueueAnnotation:
    def test_default_queue_when_no_annotation(self):
        assert default_queue_task.queue == "default"

    def test_custom_queue_stored_on_task(self):
        assert orders_task.queue == "orders"

    def test_different_queues_on_different_tasks(self):
        assert orders_task.queue != emails_task.queue

    async def test_queue_included_in_message(self):
        msg = await orders_task.send()
        assert msg.queue == "orders"

    async def test_default_queue_in_message(self):
        msg = await default_queue_task.send()
        assert msg.queue == "default"

    async def test_queue_survives_json_round_trip(self):
        msg = await orders_task.send()
        restored = TaskMessage.model_validate_json(msg.model_dump_json())
        assert restored.queue == "orders"

    def test_plain_decorator_still_works(self):
        # @app.task without parens must not break registration
        assert "test_app.default_queue_task" in app._registry

    def test_factory_decorator_registers_correctly(self):
        assert "test_app.orders_task" in app._registry


class TestQueueOverrideOnSend:
    async def test_override_replaces_task_queue(self):
        msg = await orders_task.send(queue="priority")
        assert msg.queue == "priority"

    async def test_no_override_uses_task_queue(self):
        msg = await orders_task.send()
        assert msg.queue == "orders"

    async def test_override_on_default_queue_task(self):
        msg = await default_queue_task.send(queue="urgent")
        assert msg.queue == "urgent"

    async def test_override_does_not_mutate_task_queue(self):
        await orders_task.send(queue="priority")
        assert orders_task.queue == "orders"

    async def test_override_with_delay(self):
        msg = await orders_task.send(delay=10, queue="priority")
        assert msg.queue == "priority"
        assert msg.eta is not None

    async def test_override_published_to_correct_queue(self):
        await orders_task.send(queue="vip")
        assert app.broker.published[-1].queue == "vip"
