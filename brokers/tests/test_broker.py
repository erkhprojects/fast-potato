from __future__ import annotations

import pytest

import brokers
import call_params
import driver


# --- AbstractBroker contract ---

class TestAbstractBrokerContract:
    def test_cannot_instantiate_abstract_broker(self):
        with pytest.raises(TypeError):
            brokers.base.AbstractBroker()  # type: ignore[abstract]

    def test_concrete_subclass_must_implement_all_methods(self):
        class Incomplete(brokers.base.AbstractBroker):
            async def connect(self): ...
            async def disconnect(self): ...
            async def publish(self, msg): ...
            # consume missing

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]

    def test_missing_broker_raises_on_app_init(self):
        with pytest.raises(ValueError, match="requires a broker"):
            driver.app.FastPotato("test", broker=None)  # type: ignore[arg-type]


# --- Context manager lifecycle ---

class TestBrokerLifecycle:
    async def test_connect_called_on_enter(self):
        broker = brokers.memory.MemoryBroker()
        assert not broker.connected
        async with broker:
            assert broker.connected

    async def test_disconnect_called_on_exit(self):
        broker = brokers.memory.MemoryBroker()
        async with broker:
            pass
        assert not broker.connected


# --- Publish via Task.send() ---

class TestBrokerPublish:
    async def test_send_publishes_to_broker(self):
        broker = brokers.memory.MemoryBroker()
        app = driver.app.FastPotato("test", broker=broker)

        @app.task
        async def my_task(x: int) -> None: ...

        await my_task.send(42)
        assert len(broker.published) == 1
        assert broker.published[0].args == [42]

    async def test_published_message_has_correct_queue(self):
        broker = brokers.memory.MemoryBroker()
        app = driver.app.FastPotato("test", broker=broker)

        @app.task(queue="payments")
        async def pay(order_id: int) -> None: ...

        await pay.send(order_id=99)
        assert broker.published[0].queue == "payments"

    async def test_published_message_has_correct_task_name(self):
        broker = brokers.memory.MemoryBroker()
        app = driver.app.FastPotato("test", broker=broker)

        @app.task
        async def process(x: int) -> None: ...

        await process.send(1)
        assert broker.published[0].task_name.startswith("test.")
        assert broker.published[0].task_name.endswith(".process")

    async def test_multiple_tasks_publish_to_same_broker(self):
        broker = brokers.memory.MemoryBroker()
        app = driver.app.FastPotato("test", broker=broker)

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
        class BrokerA(brokers.base.AbstractBroker):
            published: list[call_params.message.TaskMessage] = []
            async def connect(self): ...
            async def disconnect(self): ...
            async def publish(self, msg): self.published.append(msg)
            async def consume(self, queues): return; yield  # noqa: unreachable

        class BrokerB(brokers.base.AbstractBroker):
            published: list[call_params.message.TaskMessage] = []
            async def connect(self): ...
            async def disconnect(self): ...
            async def publish(self, msg): self.published.append(msg)
            async def consume(self, queues): return; yield  # noqa: unreachable

        broker_a, broker_b = BrokerA(), BrokerB()
        app_a = driver.app.FastPotato("app", broker=broker_a)
        app_b = driver.app.FastPotato("app", broker=broker_b)

        @app_a.task
        async def task_fn(x: int) -> None: ...

        @app_b.task
        async def task_fn_b(x: int) -> None: ...

        await task_fn.send(1)
        await task_fn_b.send(2)

        assert broker_a.published[0].args == [1]
        assert broker_b.published[0].args == [2]
