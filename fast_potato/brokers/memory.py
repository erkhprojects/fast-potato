from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

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
        self._notify_event: asyncio.Event = asyncio.Event()

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def publish(self, msg: message.TaskMessage) -> None:
        self.published.append(msg)
        self.history.append(msg)
        self._notify_event.set()

    async def has_messages(self, queues: list[str]) -> bool:
        """Return True if any pending message matches the given queues."""
        return any(m.queue in queues for m in self.published)

    async def consume(self, queues: list[str]) -> AsyncGenerator[message.TaskMessage]:
        while True:
            found: message.TaskMessage | None = None
            for i, msg in enumerate(self.published):
                if msg.queue in queues:
                    found = self.published.pop(i)
                    break

            if found is not None:
                yield found
                continue

            self._notify_event.clear()
            await self._notify_event.wait()
