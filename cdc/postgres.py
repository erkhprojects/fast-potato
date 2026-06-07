from __future__ import annotations

import asyncio
import struct
from collections.abc import AsyncIterator
from typing import Any

import psycopg

from cdc.base import AbstractCDCBroker, ChangeEvent, Operation

_INSERT = ord("I")
_UPDATE = ord("U")
_DELETE = ord("D")
_RELATION = ord("R")


def _read_str(data: bytes, offset: int) -> tuple[str, int]:
    end = data.index(b"\x00", offset)
    return data[offset:end].decode(), end + 1


def _read_tuple(
    data: bytes, offset: int, columns: list[str]
) -> tuple[dict[str, Any], int]:
    n = struct.unpack_from(">H", data, offset)[0]
    offset += 2
    row: dict[str, Any] = {}
    for i in range(n):
        kind = data[offset]
        offset += 1
        name = columns[i] if i < len(columns) else f"col{i}"
        if kind == ord("n"):
            row[name] = None
        elif kind == ord("u"):
            row[name] = None
        elif kind == ord("t"):
            length = struct.unpack_from(">I", data, offset)[0]
            offset += 4
            row[name] = data[offset : offset + length].decode()
            offset += length
    return row, offset


class PostgresCDCBroker(AbstractCDCBroker):
    def __init__(
        self,
        dsn: str,
        slot_name: str = "fast_potato_cdc",
        publication_name: str = "fast_potato_pub",
        poll_interval: float = 0.5,
    ) -> None:
        self._dsn = dsn
        self._slot_name = slot_name
        self._pub_name = publication_name
        self._poll_interval = poll_interval
        self._conn: psycopg.AsyncConnection | None = None
        self._relations: dict[int, tuple[str, list[str]]] = {}

    async def connect(self) -> None:
        self._conn = await psycopg.AsyncConnection.connect(self._dsn, autocommit=True)
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT 1 FROM pg_publication WHERE pubname = %s", [self._pub_name]
            )
            if not await cur.fetchone():
                await cur.execute(
                    f"CREATE PUBLICATION {self._pub_name} FOR ALL TABLES"
                )
            await cur.execute(
                "SELECT 1 FROM pg_replication_slots WHERE slot_name = %s",
                [self._slot_name],
            )
            if not await cur.fetchone():
                await cur.execute(
                    "SELECT pg_create_logical_replication_slot(%s, 'pgoutput')",
                    [self._slot_name],
                )

    async def disconnect(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def stream(self) -> AsyncIterator[ChangeEvent]:
        assert self._conn is not None
        while True:
            async with self._conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT data FROM pg_logical_slot_get_binary_changes(
                        %s, NULL, NULL,
                        'proto_version', '1',
                        'publication_names', %s
                    )
                    """,
                    [self._slot_name, self._pub_name],
                )
                rows = await cur.fetchall()

            for (raw,) in rows:
                data = bytes(raw) if isinstance(raw, memoryview) else raw
                event = self._parse(data)
                if event is not None:
                    yield event

            await asyncio.sleep(self._poll_interval)

    def _parse(self, data: bytes) -> ChangeEvent | None:
        if not data:
            return None
        msg = data[0]

        if msg == _RELATION:
            offset = 1
            oid = struct.unpack_from(">I", data, offset)[0]
            offset += 4
            _namespace, offset = _read_str(data, offset)
            table, offset = _read_str(data, offset)
            offset += 1  # replica identity
            n_cols = struct.unpack_from(">H", data, offset)[0]
            offset += 2
            cols: list[str] = []
            for _ in range(n_cols):
                offset += 1  # flags
                name, offset = _read_str(data, offset)
                offset += 8  # type OID + modifier
                cols.append(name)
            self._relations[oid] = (table, cols)
            return None

        if msg == _INSERT:
            oid = struct.unpack_from(">I", data, 1)[0]
            table, cols = self._relations.get(oid, ("unknown", []))
            after, _ = _read_tuple(data, 6, cols)  # skip OID(4) + 'N'(1)
            return ChangeEvent(op=Operation.INSERT, source=table, after=after)

        if msg == _UPDATE:
            oid = struct.unpack_from(">I", data, 1)[0]
            table, cols = self._relations.get(oid, ("unknown", []))
            marker = data[5]
            offset = 6
            before = None
            if marker in (ord("K"), ord("O")):
                before, offset = _read_tuple(data, offset, cols)
                offset += 1  # skip 'N'
            after, _ = _read_tuple(data, offset, cols)
            return ChangeEvent(op=Operation.UPDATE, source=table, before=before, after=after)

        if msg == _DELETE:
            oid = struct.unpack_from(">I", data, 1)[0]
            table, cols = self._relations.get(oid, ("unknown", []))
            before, _ = _read_tuple(data, 6, cols)  # skip OID(4) + marker(1)
            return ChangeEvent(op=Operation.DELETE, source=table, before=before)

        return None
