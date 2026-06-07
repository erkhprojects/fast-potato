"""Unit tests for the on_change decorator — no external services needed."""
from __future__ import annotations

import pytest

from brokers.memory import MemoryBroker
from cdc.base import ChangeEvent, Operation
from core.app import FastPotato


def make_app(cdc=None):
    return FastPotato("test_app", broker=MemoryBroker(), cdc=cdc)


async def test_on_change_registers_handler():
    app = make_app()

    @app.on_change(table="orders", op=["insert"])
    async def handler(event: ChangeEvent): ...

    assert list(app._cdc_registry.items())[0] == (("orders", Operation.INSERT), [handler])


async def test_on_change_default_ops():
    app = make_app()

    @app.on_change(table="users")
    async def handler(event: ChangeEvent): ...

    assert ("users", Operation.INSERT) in app._cdc_registry
    assert ("users", Operation.UPDATE) in app._cdc_registry
    assert ("users", Operation.DELETE) in app._cdc_registry


async def test_on_change_dispatches_correct_handler():
    app = make_app()
    received = []

    @app.on_change(table="orders", op=["insert"])
    async def on_insert(event: ChangeEvent):
        received.append(event)

    event = ChangeEvent(op=Operation.INSERT, source="orders", after={"id": 1})
    await app._dispatch_cdc_event(event)
    assert len(received) == 1
    assert received[0].after == {"id": 1}


async def test_on_change_ignores_wrong_table():
    app = make_app()
    received = []

    @app.on_change(table="orders", op=["insert"])
    async def on_insert(event: ChangeEvent):
        received.append(event)

    event = ChangeEvent(op=Operation.INSERT, source="payments", after={"id": 2})
    await app._dispatch_cdc_event(event)
    assert received == []


async def test_on_change_collection_alias():
    app = make_app()

    @app.on_change(collection="products", op=["update"])
    async def handler(event: ChangeEvent): ...

    assert ("products", Operation.UPDATE) in app._cdc_registry


async def test_raises_without_source():
    app = make_app()
    with pytest.raises(ValueError):

        @app.on_change(op=["insert"])
        async def handler(event): ...
