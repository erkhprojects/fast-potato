from __future__ import annotations

import asyncio

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from cdc.base import Operation
from cdc.mongo import MongoCDCBroker

pytestmark = pytest.mark.integration

DB = "fastpotato_test"


@pytest.fixture(autouse=True)
async def drop_collection(mongo_uri: str) -> None:
    yield
    client = AsyncIOMotorClient(mongo_uri)
    await client[DB]["orders"].drop()
    client.close()


async def test_mongo_cdc_insert(mongo_uri: str) -> None:
    broker = MongoCDCBroker(uri=mongo_uri, db=DB)
    events = []

    async def collect() -> None:
        async with broker:
            async for event in broker.stream():
                events.append(event)
                break

    async def insert() -> None:
        await asyncio.sleep(0.5)
        client = AsyncIOMotorClient(mongo_uri)
        await client[DB]["orders"].insert_one({"item": "widget", "qty": 5})
        client.close()

    await asyncio.gather(collect(), insert())

    assert len(events) == 1
    assert events[0].op == Operation.INSERT
    assert events[0].source == "orders"
    assert events[0].after["item"] == "widget"


async def test_mongo_cdc_update(mongo_uri: str) -> None:
    broker = MongoCDCBroker(uri=mongo_uri, db=DB)
    events = []

    async def collect() -> None:
        async with broker:
            async for event in broker.stream():
                if event.op == Operation.UPDATE:
                    events.append(event)
                    break

    async def mutate() -> None:
        await asyncio.sleep(0.5)
        client = AsyncIOMotorClient(mongo_uri)
        col = client[DB]["orders"]
        result = await col.insert_one({"item": "gadget", "qty": 1})
        await col.update_one({"_id": result.inserted_id}, {"$set": {"qty": 99}})
        client.close()

    await asyncio.gather(collect(), mutate())

    assert len(events) == 1
    assert events[0].op == Operation.UPDATE
    assert events[0].after["qty"] == 99


async def test_mongo_cdc_delete(mongo_uri: str) -> None:
    broker = MongoCDCBroker(uri=mongo_uri, db=DB)
    events = []

    async def collect() -> None:
        async with broker:
            async for event in broker.stream():
                if event.op == Operation.DELETE:
                    events.append(event)
                    break

    async def mutate() -> None:
        await asyncio.sleep(0.5)
        client = AsyncIOMotorClient(mongo_uri)
        col = client[DB]["orders"]
        result = await col.insert_one({"item": "to_delete"})
        await col.delete_one({"_id": result.inserted_id})
        client.close()

    await asyncio.gather(collect(), mutate())

    assert len(events) == 1
    assert events[0].op == Operation.DELETE
