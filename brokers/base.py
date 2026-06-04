from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from ingestor.message import TaskMessage


class AbstractBroker(ABC):
    """
    Strategy interface for all broker implementations.

    Subclass this to add a new broker (Redis, RabbitMQ, SQS, etc.).
    Implement the four abstract methods and the rest is handled for you.

    Usage:
        class MyBroker(AbstractBroker):
            async def connect(self): ...
            async def disconnect(self): ...
            async def publish(self, message): ...
            async def consume(self, queues): ...

        async with MyBroker(...) as broker:
            app = FastPotato("my_app", broker=broker)
    """

    @abstractmethod
    async def connect(self) -> None:
        """Open the connection to the broker."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the connection cleanly."""

    @abstractmethod
    async def publish(self, message: TaskMessage) -> None:
        """
        Push a message onto the queue named in message.queue.
        Implementations must respect message.eta for delayed delivery.
        """

    @abstractmethod
    def consume(self, queues: list[str]) -> AsyncIterator[TaskMessage]:
        """
        Yield TaskMessages from the given queues indefinitely.
        Implementations must be async generators or return one.
        """

    async def __aenter__(self) -> AbstractBroker:
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.disconnect()
