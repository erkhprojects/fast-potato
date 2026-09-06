from __future__ import annotations

import asyncio
from typing import Annotated, Any

import pytest
from pydantic import BaseModel

from fast_potato import Depends, FastPotato, Potato, TaskMessage, Worker
from fast_potato.brokers import MemoryBroker


class Address(BaseModel):
    city: str
    country: str


class User(BaseModel):
    name: str
    age: int
    address: Address | None = None


class AppConfig(Potato):
    env: str = "test"


def make_app() -> tuple[FastPotato, MemoryBroker]:
    broker = MemoryBroker()
    app = FastPotato("test_worker_app", broker=broker, potato=AppConfig(env="production"))
    return app, broker


class TestWorkerBasicExecution:
    async def test_process_one_simple_task(self):
        app, broker = make_app()

        @app.task
        async def add(x: int, y: int) -> int:
            return x + y

        msg = await add.send(10, 20)
        worker = Worker(app=app)
        result = await worker.process_one(msg)
        assert result == 30

    async def test_run_until_empty_processes_all(self):
        app, broker = make_app()
        results = []

        @app.task
        async def record(val: int) -> None:
            results.append(val)

        await record.send(1)
        await record.send(2)
        await record.send(3)

        assert len(broker.published) == 3
        worker = Worker(app=app)
        count = await worker.run_until_empty()

        assert count == 3
        assert results == [1, 2, 3]
        assert len(broker.published) == 0


class TestWorkerPydanticDeserialization:
    async def test_deserialize_single_pydantic_model(self):
        app, broker = make_app()

        @app.task
        async def get_user_name(user: User) -> str:
            assert isinstance(user, User)
            return user.name

        user = User(name="Alice", age=30)
        msg = await get_user_name.send(user)

        worker = Worker(app=app)
        result = await worker.process_one(msg)
        assert result == "Alice"

    async def test_deserialize_nested_pydantic_model(self):
        app, broker = make_app()

        @app.task
        async def get_city(user: User) -> str:
            assert isinstance(user, User)
            assert isinstance(user.address, Address)
            return user.address.city

        user = User(name="Bob", age=25, address=Address(city="Tokyo", country="JP"))
        msg = await get_city.send(user)

        worker = Worker(app=app)
        result = await worker.process_one(msg)
        assert result == "Tokyo"

    async def test_deserialize_list_of_models(self):
        app, broker = make_app()

        @app.task
        async def count_users(users: list[User]) -> int:
            for u in users:
                assert isinstance(u, User)
            return len(users)

        u1 = User(name="User1", age=20)
        u2 = User(name="User2", age=22)
        msg = await count_users.send([u1, u2])

        worker = Worker(app=app)
        result = await worker.process_one(msg)
        assert result == 2

    async def test_deserialize_optional_model(self):
        app, broker = make_app()

        @app.task
        async def check_user(user: User | None) -> str:
            if user is None:
                return "empty"
            assert isinstance(user, User)
            return user.name

        msg1 = await check_user.send(User(name="Charlie", age=35))
        worker = Worker(app=app)
        assert await worker.process_one(msg1) == "Charlie"


async def get_suffix() -> str:
    return "!!!"


class TestWorkerDependencyInjection:
    async def test_task_with_sync_and_async_deps(self):
        app, broker = make_app()

        def get_sync_val() -> int:
            return 100

        async def get_async_val() -> int:
            return 200

        @app.task
        async def compute(
            x: int,
            sync_val: int = Depends(get_sync_val),
            async_val: int = Depends(get_async_val),
        ) -> int:
            return x + sync_val + async_val

        msg = await compute.send(5)
        worker = Worker(app=app)
        result = await worker.process_one(msg)
        assert result == 305

    async def test_generator_dependency_teardown(self):
        app, broker = make_app()
        events = []

        def get_resource():
            events.append("acquire")
            yield "resource"
            events.append("release")

        @app.task
        async def use_res(r: str = Depends(get_resource)) -> str:
            events.append(f"use_{r}")
            return r

        msg = await use_res.send()
        worker = Worker(app=app)
        result = await worker.process_one(msg)

        assert result == "resource"
        assert events == ["acquire", "use_resource", "release"]

    async def test_potato_dependency(self):
        app, broker = make_app()

        @app.task
        async def get_env(cfg: AppConfig = Depends[AppConfig]) -> str:
            return cfg.env

        msg = await get_env.send()
        worker = Worker(app=app)
        result = await worker.process_one(msg)
        assert result == "production"

    async def test_annotated_dependency(self):
        app, broker = make_app()

        @app.task
        async def shout(text: str, s: Annotated[str, Depends(get_suffix)]) -> str:
            return f"{text}{s}"

        msg = await shout.send("hello")
        worker = Worker(app=app)
        assert await worker.process_one(msg) == "hello!!!"


class TestWorkerResilience:
    async def test_failing_task_raises_on_process_one(self):
        app, broker = make_app()

        @app.task
        async def fail() -> None:
            raise ValueError("Task error")

        msg = await fail.send()
        worker = Worker(app=app)

        with pytest.raises(ValueError, match="Task error"):
            await worker.process_one(msg)

    async def test_safe_execute_suppresses_exception_and_logs(self):
        app, broker = make_app()

        @app.task
        async def boom() -> None:
            raise RuntimeError("Explosion")

        msg = await boom.send()
        worker = Worker(app=app)

        result = await worker._safe_execute(msg)
        assert result is None

    async def test_unknown_task_raises_key_error(self):
        app, broker = make_app()
        worker = Worker(app=app)
        bad_msg = TaskMessage(task_name="nonexistent.task")

        with pytest.raises(KeyError):
            await worker.process_one(bad_msg)


class TestWorkerQueues:
    async def test_multiple_queues_filtering(self):
        app, broker = make_app()
        handled = []

        @app.task(queue="orders")
        async def order_task(i: int) -> None:
            handled.append(("orders", i))

        @app.task(queue="emails")
        async def email_task(i: int) -> None:
            handled.append(("emails", i))

        await order_task.send(1)
        await email_task.send(2)

        # Worker only listens to orders
        worker = Worker(app=app, queues=["orders"])
        count = await worker.run_until_empty()

        assert count == 1
        assert handled == [("orders", 1)]
        # emails task still unconsumed in broker
        assert len(broker.published) == 1
        assert broker.published[0].queue == "emails"


class TestWorkerConcurrency:
    async def test_semaphore_bounds_concurrency(self):
        app, broker = make_app()
        active = 0
        peak_active = 0

        @app.task
        async def slow_job() -> None:
            nonlocal active, peak_active
            active += 1
            if active > peak_active:
                peak_active = active
            await asyncio.sleep(0.05)
            active -= 1

        for _ in range(6):
            await slow_job.send()

        worker = Worker(app=app, concurrency=2)

        run_task = asyncio.create_task(worker.run())
        # wait briefly for tasks to be processed
        await asyncio.sleep(0.2)
        worker.stop()
        await run_task

        assert peak_active <= 2
