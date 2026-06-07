from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from cdc.base import AbstractCDCBroker, ChangeEvent, Operation

_OP_MAP: dict[str, Operation] = {
    "insert": Operation.INSERT,
    "update": Operation.UPDATE,
    "replace": Operation.UPDATE,
    "delete": Operation.DELETE,
}


def _stringify_id(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if doc and "_id" in doc:
        return {**doc, "_id": str(doc["_id"])}
    return doc


class MongoCDCBroker(AbstractCDCBroker):
    def __init__(self, uri: str, db: str, poll_interval: float = 0.0) -> None:
        self._uri = uri
        self._db_name = db
        self._client: AsyncIOMotorClient | None = None
        self._db = None

    async def connect(self) -> None:
        self._client = AsyncIOMotorClient(self._uri)
        self._db = self._client[self._db_name]

    async def disconnect(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
            self._db = None

    async def stream(self) -> AsyncIterator[ChangeEvent]:
        assert self._db is not None
        async with self._db.watch(full_document="updateLookup") as change_stream:
            async for change in change_stream:
                op_type = change.get("operationType", "")
                if op_type not in _OP_MAP:
                    continue
                collection = change.get("ns", {}).get("coll", "")
                full_doc = _stringify_id(change.get("fullDocument"))
                doc_key = change.get("documentKey", {})
                if "_id" in doc_key:
                    doc_key = {"_id": str(doc_key["_id"])}
                before = doc_key if op_type == "delete" else None
                yield ChangeEvent(
                    op=_OP_MAP[op_type],
                    source=collection,
                    before=before,
                    after=full_doc,
                    metadata={"db": self._db_name},
                )
