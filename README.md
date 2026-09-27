<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-dark.svg">
    <img src="docs/assets/logo.svg" alt="fast-potato" width="420">
  </picture>
</p>

An async-first distributed task queue for Python, built on `asyncio` and Pydantic.
Think Celery, but with async tasks, FastAPI-style dependency injection, and
**type-safe** task calls.

- **Type-safe:** every task takes a Pydantic model as its input, and `send()`
  is fully typed. mypy catches wrong or missing task data before your code runs.
- **Pydantic handles serialization:** no custom encoders. Your models are the wire format.
- **Dependency injection** with `Depends(...)`, including `yield` setup and teardown.
- **Built-in testing:** run tasks in-process with `TestApp`.
- **Redis and RabbitMQ** brokers, cron scheduling, and multi-process workers.

## Install

Requires Python 3.14+.

```bash
pip install "fast-potato[redis]"      # or [rabbitmq], or [all]
```

## Quick start

```python
# shop.py
from pydantic import BaseModel

from fast_potato import FastPotato
from fast_potato.brokers import RedisBroker

app = FastPotato("shop", broker=RedisBroker("redis://localhost:6379/0"))


class Order(BaseModel):
    order_id: int
    email: str


@app.task
async def send_receipt(order: Order) -> None:
    print(f"receipt for #{order.order_id} sent to {order.email}")


async def checkout() -> None:
    await send_receipt.send(Order(order_id=1, email="alice@example.com"))
    await send_receipt.send(Order(order_id=2, email="bob@example.com"), delay=60)
```

`send()` connects to the broker on first use. If the broker is unreachable, it
raises `BrokerConnectionError` after a timeout instead of hanging.

Run a worker:

```bash
fast-potato -A shop:app
```

### mypy catches bad calls

```python
await send_receipt.send({"order_id": 1})
# error: Argument 1 to "send" of "Task" has incompatible type "dict[str, int]"; expected "Order"

await send_receipt.send()
# error: Missing positional argument "data" in call to "send" of "Task"
```

## Dependency injection

Parameters after the input are resolved on the worker and never sent:

```python
from collections.abc import AsyncIterator
from typing import Annotated

from fast_potato import Depends, Potato


class AppConfig(Potato):  # app-wide config, created once
    currency: str = "EUR"


async def get_db() -> AsyncIterator[Database]:
    db = await Database.connect()
    try:
        yield db
    finally:
        await db.close()  # teardown after the task finishes


@app.task
async def place_order(
    order: Order,
    db: Annotated[Database, Depends(get_db)],
    config: Annotated[AppConfig, Depends()],
) -> None:
    await db.save(order, currency=config.currency)


await place_order.send(order)  # db and config are injected on the worker
```

## Testing

`TestApp` runs tasks in-process through the same code path as a real worker,
with dependency overrides:

```python
from fast_potato.testing import TestApp


async def test_checkout() -> None:
    with TestApp(app) as t:  # drain mode: send() only queues
        t.override(get_db, get_fake_db)

        await checkout()
        t.assert_sent(send_receipt, Order(order_id=1, email="alice@example.com"))
        await t.drain()  # run everything that was queued


async def test_checkout_eager() -> None:
    with TestApp(app, eager=True):  # every send() runs immediately
        await checkout()
```

A complete example with pytest fixtures is in [`examples/testing/`](examples/testing/).

## Documentation

The full, example-based docs are in [`docs/`](docs/), available in English,
German, Spanish and French. Preview them locally:

```bash
uv run --group docs mkdocs serve
```

## License

MIT
