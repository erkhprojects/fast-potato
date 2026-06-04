from __future__ import annotations

from collections.abc import AsyncIterator

try:
    import aio_pika  # noqa: F401
except ImportError as exc:
    raise ImportError(
        "RabbitMQBroker requires the 'rabbitmq' extra: pip install fast-potato[rabbitmq]"
    ) from exc

from brokers.base import AbstractBroker
from core.message import TaskMessage


class RabbitMQBroker(AbstractBroker):
    """
    RabbitMQ broker using aio-pika.

    Args:
        url: AMQP connection URL, e.g. "amqp://guest:guest@localhost/"
    """

    def __init__(self, url: str = "amqp://guest:guest@localhost/") -> None:
        self._url = url
        # connection and channel wired up in Phase 3
        self._connection = None
        self._channel = None

    async def connect(self) -> None:
        raise NotImplementedError("RabbitMQBroker.connect() — coming in Phase 3")

    async def disconnect(self) -> None:
        raise NotImplementedError("RabbitMQBroker.disconnect() — coming in Phase 3")

    async def publish(self, message: TaskMessage) -> None:
        raise NotImplementedError("RabbitMQBroker.publish() — coming in Phase 3")

    async def consume(self, queues: list[str]) -> AsyncIterator[TaskMessage]:
        raise NotImplementedError("RabbitMQBroker.consume() — coming in Phase 3")
        yield  # make Python treat this as an async generator
