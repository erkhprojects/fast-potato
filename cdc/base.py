from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from enum import Enum
from typing import Any

from pydantic import BaseModel


class Operation(str, Enum):
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"


class ChangeEvent(BaseModel):
    op: Operation
    source: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    metadata: dict[str, Any] = {}

    model_config = {"arbitrary_types_allowed": True}


class AbstractCDCBroker(ABC):
    """Strategy interface for CDC sources. Subclass to add new sources."""

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    def stream(self) -> AsyncIterator[ChangeEvent]:
        """Yield ChangeEvents indefinitely from the source."""

    async def __aenter__(self) -> AbstractCDCBroker:
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.disconnect()
