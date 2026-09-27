from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from fast_potato import FastPotato, TaskMessage
from fast_potato.brokers import AbstractBroker, BrokerConnectionError, MemoryBroker


class XInput(BaseModel):
    x: int


class OrderInput(BaseModel):
    order_id: int


# --- AbstractBroker contract ---


class TestAbstractBrokerContract:
    def test_cannot_instantiate_abstract_broker(self):
        with pytest.raises(TypeError):
            AbstractBroker()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_all_methods(self):
        class Incomplete(AbstractBroker):
            async def connect(self): ...
            async def disconnect(self): ...
            async def publish(self, msg): ...

            # consume missing

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]

    def test_missing_broker_raises_on_app_init(self):
        with pytest.raises(ValueError, match="requires a broker"):
            FastPotato("test", broker=None)  # type: ignore[arg-type]


# --- Context manager lifecycle ---


class TestBrokerLifecycle:
    async def test_connect_called_on_enter(self):
        broker = MemoryBroker()
        assert not broker.connected
        async with broker:
            assert broker.connected

    async def test_disconnect_called_on_exit(self):
        broker = MemoryBroker()
        async with broker:
            pass
        assert not broker.connected


# --- Publish via Task.send() ---


class TestBrokerPublish:
    async def test_send_publishes_to_broker(self):
        broker = MemoryBroker()
        app = FastPotato("test", broker=broker)

        @app.task
        async def my_task(data: XInput) -> None: ...

        await my_task.send(XInput(x=42))
        assert len(broker.published) == 1
        assert broker.published[0].payload == {"x": 42}

    async def test_published_message_has_correct_queue(self):
        broker = MemoryBroker()
        app = FastPotato("test", broker=broker)

        @app.task(queue="payments")
        async def pay(data: OrderInput) -> None: ...

        await pay.send(OrderInput(order_id=99))
        assert broker.published[0].queue == "payments"

    async def test_published_message_has_correct_task_name(self):
        broker = MemoryBroker()
        app = FastPotato("test", broker=broker)

        @app.task
        async def process(data: XInput) -> None: ...

        await process.send(XInput(x=1))
        assert broker.published[0].task_name.startswith("test.")
        assert broker.published[0].task_name.endswith(".process")

    async def test_multiple_tasks_publish_to_same_broker(self):
        broker = MemoryBroker()
        app = FastPotato("test", broker=broker)

        @app.task(queue="a")
        async def task_a() -> None: ...

        @app.task(queue="b")
        async def task_b() -> None: ...

        await task_a.send()
        await task_b.send()
        queues = {m.queue for m in broker.published}
        assert queues == {"a", "b"}


# --- Strategy: swapping brokers ---


class TestBrokerStrategy:
    async def test_swap_broker_implementations(self):
        class BrokerA(AbstractBroker):
            published: list[TaskMessage] = []

            @property
            def is_connected(self):
                return True

            async def connect(self): ...
            async def disconnect(self): ...
            async def publish(self, msg):
                self.published.append(msg)

            async def consume(self, queues):
                if False:
                    yield

        class BrokerB(AbstractBroker):
            published: list[TaskMessage] = []

            @property
            def is_connected(self):
                return True

            async def connect(self): ...
            async def disconnect(self): ...
            async def publish(self, msg):
                self.published.append(msg)

            async def consume(self, queues):
                if False:
                    yield

        broker_a, broker_b = BrokerA(), BrokerB()
        app_a = FastPotato("app", broker=broker_a)
        app_b = FastPotato("app", broker=broker_b)

        @app_a.task
        async def task_fn(data: XInput) -> None: ...

        @app_b.task
        async def task_fn_b(data: XInput) -> None: ...

        await task_fn.send(XInput(x=1))
        await task_fn_b.send(XInput(x=2))

        assert broker_a.published[0].payload == {"x": 1}
        assert broker_b.published[0].payload == {"x": 2}


# --- Lazy connect & fail-fast ---


class CountingBroker(MemoryBroker):
    def __init__(self) -> None:
        super().__init__()
        self.connect_calls = 0

    async def connect(self) -> None:
        self.connect_calls += 1
        await asyncio.sleep(0.01)  # give concurrent senders a chance to race
        await super().connect()


class TestLazyConnect:
    async def test_send_connects_on_first_use(self):
        broker = CountingBroker()
        app = FastPotato("lazy", broker=broker)

        @app.task
        async def ping() -> None: ...

        assert not broker.is_connected
        await ping.send()
        assert broker.is_connected
        assert broker.connect_calls == 1

    async def test_concurrent_first_sends_share_one_connect(self):
        broker = CountingBroker()
        app = FastPotato("lazy", broker=broker)

        @app.task
        async def ping() -> None: ...

        await asyncio.gather(*(ping.send() for _ in range(10)))
        assert broker.connect_calls == 1
        assert len(broker.history) == 10

    async def test_already_connected_broker_is_not_reconnected(self):
        broker = CountingBroker()
        await broker.connect()
        app = FastPotato("lazy", broker=broker)

        @app.task
        async def ping() -> None: ...

        await ping.send()
        assert broker.connect_calls == 1


class TestFailFast:
    @pytest.mark.parametrize(
        "make_broker",
        [
            pytest.param(
                lambda: pytest.importorskip("fast_potato.brokers.redis").RedisBroker(
                    "redis://127.0.0.1:1/0", connect_timeout=2
                ),
                id="redis",
            ),
            pytest.param(
                lambda: pytest.importorskip(
                    "fast_potato.brokers.rabbitmq"
                ).RabbitMQBroker("amqp://guest:secret@127.0.0.1:1/", connect_timeout=2),
                id="rabbitmq",
            ),
        ],
    )
    async def test_unreachable_broker_raises_on_send(self, make_broker):
        app = FastPotato("unreachable", broker=make_broker())

        @app.task
        async def ping() -> None: ...

        with pytest.raises(BrokerConnectionError) as exc_info:
            await ping.send()
        assert "secret" not in str(exc_info.value)
        assert not app.broker.is_connected

    @pytest.mark.parametrize(
        ("url", "shown"),
        [
            ("amqp://guest:secret@host:5672/", "amqp://guest:***@host:5672/"),
            ("redis://:secret@host:6379/0", "redis://:***@host:6379/0"),
            ("redis://localhost:6379/0", "redis://localhost:6379/0"),
        ],
    )
    def test_password_is_redacted(self, url, shown):
        err = BrokerConnectionError.from_exception(
            "X", url, 1.0, OSError(f"failed for {url}")
        )
        assert "secret" not in str(err)
        assert str(err).count(shown) == 2  # in the URL and in the echoed reason

    def test_error_message_names_broker_and_reason(self):
        err = BrokerConnectionError.from_exception(
            "Redis", "redis://:pw@h:1/0", 5.0, TimeoutError()
        )
        assert str(err) == (
            "Could not connect to Redis at redis://:***@h:1/0 (timeout 5.0s): TimeoutError"
        )
        assert isinstance(err, ConnectionError)
