from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated

import pytest
from pydantic import BaseModel

from fast_potato import Depends, FastPotato, Potato, TaskMessage
from fast_potato.brokers.base import AbstractBroker
from fast_potato.brokers.rabbitmq import RabbitMQBroker
from fast_potato.brokers.redis import RedisBroker
from fast_potato.worker import Worker


@pytest.fixture(params=["redis", "rabbitmq"])
async def broker(request: pytest.FixtureRequest) -> AsyncIterator[AbstractBroker]:
    """
    Parametrized broker fixture running against actual Redis and RabbitMQ.
    If a service is unreachable (e.g. running outside Docker without local services),
    the test will cleanly skip with a helpful message.
    """
    broker_type = request.param
    broker_instance: AbstractBroker

    if broker_type == "redis":
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        broker_instance = RedisBroker(url=redis_url, poll_interval=1.0)
    elif broker_type == "rabbitmq":
        rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
        broker_instance = RabbitMQBroker(url=rabbitmq_url)
    else:
        raise ValueError(f"Unknown broker type: {broker_type}")

    try:
        await broker_instance.connect()
    except Exception as exc:
        pytest.skip(f"{broker_type} is not reachable: {exc}")

    try:
        yield broker_instance
    finally:
        await broker_instance.disconnect()


# ------------------------------------------------------------------------------
# 1. Lifecycle Test
# ------------------------------------------------------------------------------


async def test_broker_lifecycle(broker: AbstractBroker) -> None:
    """Test connection and clean disconnect."""
    # Already connected by fixture; test disconnect and reconnect
    await broker.disconnect()
    await broker.connect()


# ------------------------------------------------------------------------------
# 2. Single Queue Delivery Test
# ------------------------------------------------------------------------------


async def test_publish_and_consume_single_message(
    broker: AbstractBroker,
) -> None:
    """Test publishing and immediately consuming a single message."""
    queue_name = f"int_single_{uuid.uuid4().hex[:8]}"
    msg = TaskMessage(
        task_name="tests.sample_task",
        queue=queue_name,
        payload={"number": 42, "name": "spud", "active": True},
    )

    await broker.publish(msg)

    async def _get_one() -> TaskMessage:
        async for received in broker.consume([queue_name]):
            return received
        raise RuntimeError("No message received")

    received = await asyncio.wait_for(_get_one(), timeout=5.0)

    assert received.id == msg.id
    assert received.task_name == "tests.sample_task"
    assert received.queue == queue_name
    assert received.payload == {"number": 42, "name": "spud", "active": True}


# ------------------------------------------------------------------------------
# 3. Multi-Queue Routing Test
# ------------------------------------------------------------------------------


async def test_publish_and_consume_multiple_queues(
    broker: AbstractBroker,
) -> None:
    """Test consumer listening across multiple queues receives messages from all of them."""
    q_a = f"int_multi_a_{uuid.uuid4().hex[:8]}"
    q_b = f"int_multi_b_{uuid.uuid4().hex[:8]}"

    msg_a = TaskMessage(task_name="task.a", queue=q_a, payload={"value": "alpha"})
    msg_b = TaskMessage(task_name="task.b", queue=q_b, payload={"value": "bravo"})

    await broker.publish(msg_a)
    await broker.publish(msg_b)

    received_messages: list[TaskMessage] = []

    async def _collect() -> None:
        async for m in broker.consume([q_a, q_b]):
            received_messages.append(m)
            if len(received_messages) == 2:
                break

    await asyncio.wait_for(_collect(), timeout=5.0)

    received_queues = {m.queue for m in received_messages}
    assert received_queues == {q_a, q_b}


# ------------------------------------------------------------------------------
# 4. Delayed ETA Delivery Test
# ------------------------------------------------------------------------------


async def test_delayed_eta_delivery(broker: AbstractBroker) -> None:
    """Test that messages with an ETA in the future are only delivered after the ETA."""
    queue_name = f"int_delayed_{uuid.uuid4().hex[:8]}"
    delay_seconds = 2.0
    eta = datetime.now(tz=UTC) + timedelta(seconds=delay_seconds)

    msg = TaskMessage(
        task_name="task.delayed",
        queue=queue_name,
        payload={"value": "delayed_payload"},
        eta=eta,
    )

    await broker.publish(msg)

    # 1. Immediate check: should NOT receive the message within 0.5s
    async def _try_immediate() -> TaskMessage | None:
        async for m in broker.consume([queue_name]):
            return m
        return None

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(_try_immediate(), timeout=0.5)

    # 2. Wait for delay to elapse and assert message is received
    async def _wait_for_delayed() -> TaskMessage:
        async for m in broker.consume([queue_name]):
            return m
        raise RuntimeError("Never received delayed message")

    delayed_received = await asyncio.wait_for(
        _wait_for_delayed(), timeout=delay_seconds + 5.0
    )
    assert delayed_received.id == msg.id
    assert delayed_received.payload == {"value": "delayed_payload"}


# ------------------------------------------------------------------------------
# 5. End-to-End Worker Execution Test
# ------------------------------------------------------------------------------


class OrderItem(BaseModel):
    sku: str
    quantity: int


class CustomPotato(Potato):
    tax_rate: float = 0.08


async def test_end_to_end_worker_execution(broker: AbstractBroker) -> None:
    """
    Test full end-to-end task execution with Worker, Pydantic arguments,
    and dependency injection running on real broker.
    """
    queue_name = f"int_worker_{uuid.uuid4().hex[:8]}"

    app = FastPotato("integration_app", broker=broker, potato=CustomPotato())

    execution_event = asyncio.Event()
    results: dict[str, object] = {}

    def get_currency() -> str:
        return "USD"

    @app.task(queue=queue_name)
    async def process_order(
        item: OrderItem,
        currency: str = Depends(get_currency),
        potato: CustomPotato = Depends[CustomPotato],
    ) -> None:
        results["item"] = item
        results["currency"] = currency
        results["tax_rate"] = potato.tax_rate
        execution_event.set()

    worker = Worker(app=app, queues=[queue_name], concurrency=2)
    worker_task = asyncio.create_task(worker.run())

    try:
        # Give worker a moment to establish listener
        await asyncio.sleep(0.3)

        # Dispatch task through the real broker
        order = OrderItem(sku="POTATO-123", quantity=5)
        await process_order.send(order)

        # Wait for worker to pick up and process task
        await asyncio.wait_for(execution_event.wait(), timeout=6.0)

        assert results["item"] == order
        assert results["currency"] == "USD"
        assert results["tax_rate"] == 0.08
    finally:
        # Graceful stop, like SIGTERM in deployment: signal, then wait for run() to
        # return on its own. The timeout turns a stuck shutdown into a failure.
        worker.stop()
        await asyncio.wait_for(worker_task, timeout=5.0)


# ------------------------------------------------------------------------------
# 6. End-to-End Annotated Dependency Injection Test
# ------------------------------------------------------------------------------


async def get_db_session() -> AsyncIterator[str]:
    yield "session:db_primary_active"


class Transaction(BaseModel):
    tx_id: int


async def test_end_to_end_annotated_dependencies(broker: AbstractBroker) -> None:
    """
    Test full end-to-end task execution using Annotated[T, Depends(...)] and
    Annotated[Potato, Depends] running against real brokers.
    """
    queue_name = f"int_annotated_{uuid.uuid4().hex[:8]}"
    app = FastPotato("annotated_app", broker=broker, potato=CustomPotato(tax_rate=0.15))

    execution_event = asyncio.Event()
    results: dict[str, object] = {}

    @app.task(queue=queue_name)
    async def process_transaction(
        tx: Transaction,
        session: Annotated[str, Depends(get_db_session)],
        config: Annotated[CustomPotato, Depends],
    ) -> None:
        results["tx_id"] = tx.tx_id
        results["session"] = session
        results["tax_rate"] = config.tax_rate
        execution_event.set()

    worker = Worker(app=app, queues=[queue_name], concurrency=2)
    worker_task = asyncio.create_task(worker.run())

    try:
        await asyncio.sleep(0.3)
        await process_transaction.send(Transaction(tx_id=987))

        await asyncio.wait_for(execution_event.wait(), timeout=6.0)

        assert results["tx_id"] == 987
        assert results["session"] == "session:db_primary_active"
        assert results["tax_rate"] == 0.15
    finally:
        # Graceful stop, like SIGTERM in deployment: signal, then wait for run() to
        # return on its own. The timeout turns a stuck shutdown into a failure.
        worker.stop()
        await asyncio.wait_for(worker_task, timeout=5.0)
