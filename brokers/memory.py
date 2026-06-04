from __future__ import annotations

from collections.abc import AsyncIterator

from brokers.base import AbstractBroker
from ingestor.message import TaskMessage


class MemoryBroker(AbstractBroker):
    """
    In-memory broker with no external dependencies.

    Intended for testing and local development — tasks are stored in a plain
    list and never leave the process. Not suitable for production.

    Usage:
        broker = MemoryBroker()
        app = FastPotato("my_app", broker=broker)
    """

    def __init__(self) -> None:
        self.published: list[TaskMessage] = []
        self.connected: bool = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def publish(self, message: TaskMessage) -> None:
        self.published.append(message)

    async def consume(self, queues: list[str]) -> AsyncIterator[TaskMessage]:
        for msg in self.published:
            if msg.queue in queues:
                yield msg
