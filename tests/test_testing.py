from __future__ import annotations

from typing import Annotated

import pytest
from pydantic import BaseModel

from fast_potato import Depends, FastPotato, Potato, Worker
from fast_potato.brokers import MemoryBroker
from fast_potato.testing import EagerBroker, TestApp


class User(BaseModel):
    name: str
    age: int


class AppConfig(Potato):
    env: str = "prod"


class Value(BaseModel):
    val: int


class Name(BaseModel):
    name: str


class AddInput(BaseModel):
    x: int
    y: int


def get_greeting() -> str:
    return "hello"


def make_app() -> tuple[FastPotato, MemoryBroker]:
    broker = MemoryBroker()
    return FastPotato("testing_app", broker=broker, potato=AppConfig()), broker


class TestBrokerSwap:
    async def test_tasks_declared_before_enter_use_test_broker(self):
        app, real_broker = make_app()

        @app.task
        async def ping() -> None: ...

        with TestApp(app) as t:
            await ping.send()
            assert len(t.messages) == 1
        assert real_broker.history == []

    async def test_exit_restores_broker_potato_and_overrides(self):
        app, real_broker = make_app()
        original_potato = app.potato

        with TestApp(app, potato=AppConfig(env="test")) as t:
            t.override(get_greeting, lambda: "hi")
            assert app.broker is t.broker
            assert app.potato.env == "test"

        assert app.broker is real_broker
        assert app.potato is original_potato
        assert app.dependency_overrides == {}


class TestAssertions:
    async def test_assert_sent_decodes_pydantic_args(self):
        app, _ = make_app()

        @app.task
        async def register(user: User) -> None: ...

        with TestApp(app) as t:
            await register.send(User(name="a", age=1))
            t.assert_sent(register, User(name="a", age=1))
            assert t.sent(register) == [User(name="a", age=1)]

    async def test_assert_sent_without_input(self):
        app, _ = make_app()

        @app.task
        async def ping() -> None: ...

        with TestApp(app) as t:
            with pytest.raises(AssertionError):
                t.assert_sent(ping)
            await ping.send()
            t.assert_sent(ping)
            assert t.sent(ping) == [None]

    async def test_assert_sent_fails_with_actual_calls(self):
        app, _ = make_app()

        @app.task
        async def add(data: Value) -> None: ...

        with TestApp(app) as t:
            await add.send(Value(val=1))
            with pytest.raises(AssertionError, match="Sent:"):
                t.assert_sent(add, Value(val=2))

    async def test_assert_not_sent(self):
        app, _ = make_app()

        @app.task
        async def a() -> None: ...

        @app.task
        async def b() -> None: ...

        with TestApp(app) as t:
            await a.send()
            t.assert_not_sent(b)
            with pytest.raises(AssertionError):
                t.assert_not_sent(a)


class TestDrain:
    async def test_drain_runs_chained_tasks_in_fifo_order(self):
        app, _ = make_app()
        order: list[str] = []

        @app.task
        async def child(data: Name) -> None:
            order.append(data.name)

        @app.task
        async def parent() -> None:
            order.append("parent")
            await child.send(Name(name="c1"))
            await child.send(Name(name="c2"))

        with TestApp(app) as t:
            await parent.send()
            await child.send(Name(name="sibling"))
            assert order == []
            runs = await t.drain()

        assert order == ["parent", "sibling", "c1", "c2"]
        assert len(runs) == 4

    async def test_drain_returns_results(self):
        app, _ = make_app()

        @app.task
        async def add(data: AddInput) -> int:
            return data.x + data.y

        with TestApp(app) as t:
            await add.send(AddInput(x=1, y=2))
            runs = await t.drain()
        assert runs[0].result == 3

    async def test_drain_queue_filter(self):
        app, _ = make_app()

        @app.task(queue="a")
        async def on_a() -> None: ...

        @app.task(queue="b")
        async def on_b() -> None: ...

        with TestApp(app) as t:
            await on_a.send()
            await on_b.send()
            await t.drain(queues=["a"])
            assert [m.task_name for m in t.pending] == [on_b.name]

    async def test_drain_can_leave_delayed_tasks(self):
        app, _ = make_app()

        @app.task
        async def later() -> None: ...

        with TestApp(app) as t:
            await later.send(delay=60)
            assert await t.drain(run_delayed=False) == []
            assert len(t.pending) == 1
            assert len(await t.drain()) == 1

    async def test_drain_guards_against_infinite_loop(self):
        app, _ = make_app()

        @app.task
        async def forever() -> None:
            await forever.send()

        with TestApp(app) as t:
            await forever.send()
            with pytest.raises(RuntimeError, match="re-enqueueing"):
                await t.drain(max_tasks=5)

    async def test_drain_raises_task_errors(self):
        app, _ = make_app()

        @app.task
        async def boom() -> None:
            raise ValueError("boom")

        with TestApp(app) as t:
            await boom.send()
            with pytest.raises(ValueError, match="boom"):
                await t.drain()

    async def test_drain_collects_errors_when_not_raising(self):
        app, _ = make_app()

        @app.task
        async def boom() -> None:
            raise ValueError("boom")

        @app.task
        async def ok() -> None: ...

        with TestApp(app, raise_errors=False) as t:
            await boom.send()
            await ok.send()
            runs = await t.drain()
        assert len(runs) == 2
        assert [type(r.error) for r in t.errors] == [ValueError]


class TestEager:
    async def test_send_runs_task_immediately(self):
        app, _ = make_app()
        seen: list[User] = []

        @app.task
        async def register(user: User) -> None:
            seen.append(user)

        with TestApp(app, eager=True) as t:
            assert isinstance(t.broker, EagerBroker)
            await register.send(User(name="a", age=1))
            assert seen == [User(name="a", age=1)]
            assert t.pending == []
            t.assert_sent(register, User(name="a", age=1))

    async def test_nested_sends_run_depth_first(self):
        app, _ = make_app()
        order: list[str] = []

        @app.task
        async def child() -> None:
            order.append("child")

        @app.task
        async def parent() -> None:
            order.append("parent:start")
            await child.send()
            order.append("parent:end")

        with TestApp(app, eager=True):
            await parent.send()
        assert order == ["parent:start", "child", "parent:end"]

    async def test_errors_raise_from_send(self):
        app, _ = make_app()

        @app.task
        async def boom() -> None:
            raise ValueError("boom")

        with TestApp(app, eager=True):
            with pytest.raises(ValueError, match="boom"):
                await boom.send()


class TestOverrides:
    async def test_dependency_override(self):
        app, _ = make_app()

        @app.task
        async def greet(g: Annotated[str, Depends(get_greeting)]) -> str:
            return g

        with TestApp(app) as t:
            t.override(get_greeting, lambda: "hi")
            assert await t.call(greet) == "hi"
        # restored
        with TestApp(app) as t:
            assert await t.call(greet) == "hello"

    async def test_potato_override(self):
        app, _ = make_app()

        @app.task
        async def env(config: AppConfig = Depends[AppConfig]) -> str:
            return config.env

        with TestApp(app, potato=AppConfig(env="test")) as t:
            assert await t.call(env) == "test"

    async def test_override_applies_to_real_worker(self):
        app, _ = make_app()

        @app.task
        async def greet(g: Annotated[str, Depends(get_greeting)]) -> str:
            return g

        app.dependency_overrides[get_greeting] = lambda: "hi"
        msg = await greet.send()
        assert await Worker(app).execute(msg) == "hi"


class TestCall:
    async def test_call_round_trips_args_and_raises(self):
        app, _ = make_app()

        @app.task
        async def describe(user: User) -> str:
            assert isinstance(user, User)
            return user.name

        @app.task
        async def boom() -> None:
            raise ValueError("boom")

        with TestApp(app, raise_errors=False) as t:
            assert await t.call(describe, User(name="a", age=1)) == "a"
            with pytest.raises(ValueError):
                await t.call(boom)
