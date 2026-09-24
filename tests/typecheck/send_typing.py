"""
Static typing contract for tasks, checked by mypy in tests/test_typing.py.

Lines marked ``# type: ignore`` MUST be rejected by the type checker;
mypy runs with --warn-unused-ignores, so the test fails if one is accepted.
"""

from __future__ import annotations

from typing import Annotated, assert_type

from pydantic import BaseModel

from fast_potato import Depends, FastPotato, Potato, Task
from fast_potato.brokers import MemoryBroker
from fast_potato.testing import TestApp

app = FastPotato("typing_app", broker=MemoryBroker())


class Order(BaseModel):
    order_id: int


class Other(BaseModel):
    name: str


class AppConfig(Potato):
    env: str = "prod"


def get_db() -> str:
    return "db"


@app.task
async def process(data: Order, db: Annotated[str, Depends(get_db)]) -> int:
    return data.order_id


@app.task(queue="orders")
async def process_on_queue(data: Order) -> str:
    return db_name(data)


def db_name(data: Order) -> str:
    return str(data.order_id)


@app.task
async def cleanup(db: Annotated[str, Depends(get_db)]) -> None: ...


@app.task
async def heartbeat() -> None: ...


@app.task(queue="config")
async def reload(config: Annotated[AppConfig, Depends()]) -> None: ...


assert_type(process, Task[Order, int])
assert_type(process_on_queue, Task[Order, str])
assert_type(cleanup, Task[None, None])
assert_type(heartbeat, Task[None, None])
assert_type(reload, Task[None, None])


async def sends() -> None:
    await process.send(Order(order_id=1))
    await process.send(Order(order_id=1), delay=5, queue="vip")
    await process_on_queue.send(Order(order_id=1))
    await cleanup.send()
    await heartbeat.send(delay=1)
    await reload.send()

    await process.send()  # type: ignore
    await process.send({"order_id": 1})  # type: ignore
    await process.send(Other(name="x"))  # type: ignore
    await process.send(Order(order_id=1), db="x")  # type: ignore
    await cleanup.send(Order(order_id=1))  # type: ignore


async def testing_helpers(t: TestApp) -> None:
    assert_type(await t.call(process, Order(order_id=1)), int)
    assert_type(await t.call(cleanup), None)
    assert_type(t.sent(process), list[Order])
    t.assert_sent(process, Order(order_id=1))
    t.assert_sent(heartbeat)

    await t.call(process)  # type: ignore
    t.assert_sent(process, Other(name="x"))  # type: ignore
