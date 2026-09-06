from __future__ import annotations

from collections.abc import AsyncIterator

from fast_potato import message
from fast_potato.brokers import base


class MemoryBroker(base.AbstractBroker):
    """
    In-memory broker with no external dependencies.

    Intended for testing and local development — tasks are stored in a plain
    list and never leave the process. Not suitable for production.

    Usage:
        broker = MemoryBroker()
        app = FastPotato("my_app", broker=broker)
    """

    def __init__(self) -> None:
        self.published: list[message.TaskMessage] = []
        self.history: list[message.TaskMessage] = []
        self.connected: bool = False

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def publish(self, msg: message.TaskMessage) -> None:
        self.published.append(msg)
        self.history.append(msg)

    async def consume(self, queues: list[str]) -> AsyncIterator[message.TaskMessage]:
        i = 0
        while i < len(self.published):
            msg = self.published[i]
            if msg.queue in queues:
                self.published.pop(i)
                yield msg
            else:
                i += 1
