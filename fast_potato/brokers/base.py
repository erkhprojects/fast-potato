from __future__ import annotations

import asyncio
import re
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator

from fast_potato import message

DEFAULT_CONNECT_TIMEOUT = 5.0


class BrokerConnectionError(ConnectionError):
    """Raised when a broker can't be reached within its connect timeout."""

    # "scheme://user:password@host" -> "scheme://user:***@host"
    _URL_PASSWORD = re.compile(r"(://[^:/@]*:)[^@/]*@")

    @classmethod
    def from_exception(
        cls,
        broker_name: str,
        url: str,
        timeout: float,
        exc: BaseException,
    ) -> BrokerConnectionError:
        reason = str(exc) or type(exc).__name__
        text = (
            f"Could not connect to {broker_name} at {url} "
            f"(timeout {timeout}s): {reason}"
        )
        # Redact the whole message, so a password echoed in `reason` is hidden too.
        return cls(cls._URL_PASSWORD.sub(r"\1***@", text))


class AbstractBroker(ABC):
    """
    Strategy interface for all broker implementations.

    Subclass this to add a new broker (Redis, RabbitMQ, SQS, etc.).
    Implement the abstract members and the rest is handled for you.

    Connecting is lazy: Task.send() calls ensure_connected(), which connects on
    first use. Call connect() (or use ``async with broker:``) yourself to fail at
    startup instead, and to disconnect cleanly on shutdown.

    Usage:
        class MyBroker(AbstractBroker):
            @property
            def is_connected(self): ...
            async def connect(self): ...
            async def disconnect(self): ...
            async def publish(self, message): ...
            async def consume(self, queues): ...

        async with MyBroker(...) as broker:
            app = FastPotato("my_app", broker=broker)
    """

    # Class-level defaults so subclasses don't need to call super().__init__().
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT
    _connect_lock: asyncio.Lock | None = None

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Whether the broker currently holds an open connection."""

    @abstractmethod
    async def connect(self) -> None:
        """
        Open the connection to the broker.

        Implementations must raise BrokerConnectionError, not hang, when the
        broker is unreachable within ``connect_timeout`` seconds.
        """

    async def ensure_connected(self) -> None:
        """Connect if not connected yet; concurrent callers share one attempt."""
        if self.is_connected:
            return
        if self._connect_lock is None:
            self._connect_lock = asyncio.Lock()
        async with self._connect_lock:
            if not self.is_connected:
                await self.connect()

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the connection cleanly."""

    @abstractmethod
    async def publish(self, msg: message.TaskMessage) -> None:
        """
        Push a message onto the queue named in msg.queue.
        Implementations must respect msg.eta for delayed delivery.
        """

    @abstractmethod
    def consume(self, queues: list[str]) -> AsyncGenerator[message.TaskMessage]:
        """
        Yield TaskMessages from the given queues indefinitely.
        Implementations must be async generators or return one.
        """

    async def __aenter__(self) -> AbstractBroker:
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.disconnect()
