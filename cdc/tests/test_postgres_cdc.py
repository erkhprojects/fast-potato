from __future__ import annotations

import asyncio

import psycopg
import pytest

from cdc.base import Operation
from cdc.postgres import PostgresCDCBroker

pytestmark = pytest.mark.integration

SLOT = "test_fast_potato_cdc"
PUB = "fast_potato_pub"


@pytest.fixture(autouse=True)
async def cleanup(postgres_dsn: str) -> None:
    yield
    async with await psycopg.AsyncConnection.connect(postgres_dsn, autocommit=True) as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT pg_drop_replication_slot(%s)"
                " FROM pg_replication_slots WHERE slot_name = %s",
                [SLOT, SLOT],
            )
            await cur.execute(
                "DROP PUBLICATION IF EXISTS fast_potato_pub"
            )


async def test_postgres_cdc_insert(postgres_dsn: str) -> None:
    broker = PostgresCDCBroker(dsn=postgres_dsn, slot_name=SLOT)
    events = []

    async def collect() -> None:
        async with broker:
            async with await psycopg.AsyncConnection.connect(
                postgres_dsn, autocommit=True
            ) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "CREATE TABLE IF NOT EXISTS cdc_test"
                        " (id serial primary key, name text)"
                    )
            async for event in broker.stream():
                events.append(event)
                break

    async def insert() -> None:
        await asyncio.sleep(0.5)
        async with await psycopg.AsyncConnection.connect(
            postgres_dsn, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute("INSERT INTO cdc_test (name) VALUES ('hello')")

    await asyncio.gather(collect(), insert())

    assert len(events) == 1
    assert events[0].op == Operation.INSERT
    assert events[0].source == "cdc_test"
    assert events[0].after["name"] == "hello"


async def test_postgres_cdc_update(postgres_dsn: str) -> None:
    broker = PostgresCDCBroker(dsn=postgres_dsn, slot_name=SLOT)
    events = []

    async def collect() -> None:
        async with broker:
            async for event in broker.stream():
                if event.op == Operation.UPDATE:
                    events.append(event)
                    break

    async def mutate() -> None:
        await asyncio.sleep(0.5)
        async with await psycopg.AsyncConnection.connect(
            postgres_dsn, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "CREATE TABLE IF NOT EXISTS cdc_test2"
                    " (id serial primary key, val text)"
                )
                await cur.execute("INSERT INTO cdc_test2 (val) VALUES ('old')")
                await cur.execute("UPDATE cdc_test2 SET val = 'new' WHERE val = 'old'")

    await asyncio.gather(collect(), mutate())

    assert len(events) == 1
    assert events[0].op == Operation.UPDATE
    assert events[0].after["val"] == "new"


async def test_postgres_cdc_delete(postgres_dsn: str) -> None:
    broker = PostgresCDCBroker(dsn=postgres_dsn, slot_name=SLOT)
    events = []

    async def collect() -> None:
        async with broker:
            async for event in broker.stream():
                if event.op == Operation.DELETE:
                    events.append(event)
                    break

    async def mutate() -> None:
        await asyncio.sleep(0.5)
        async with await psycopg.AsyncConnection.connect(
            postgres_dsn, autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "CREATE TABLE IF NOT EXISTS cdc_test3"
                    " (id serial primary key, val text)"
                    " WITH (REPLICA IDENTITY = DEFAULT)"
                )
                await cur.execute("INSERT INTO cdc_test3 (val) VALUES ('bye')")
                await cur.execute("DELETE FROM cdc_test3 WHERE val = 'bye'")

    await asyncio.gather(collect(), mutate())

    assert len(events) == 1
    assert events[0].op == Operation.DELETE
