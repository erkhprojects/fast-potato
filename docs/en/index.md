# fast-potato

An async-first distributed task queue for Python, built on `asyncio` and Pydantic.

```python
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
```

## Type-safe by design

Every task takes a Pydantic model as its input, and `send()` is fully typed.
mypy (or pyright) catches wrong or missing data before your code runs:

```python
await send_receipt.send({"order_id": 1})
# error: Argument 1 to "send" of "Task" has incompatible type "dict[str, int]"; expected "Order"

await send_receipt.send()
# error: Missing positional argument "data" in call to "send" of "Task"
```

## Features

- **Pydantic in, Pydantic out**: Pydantic handles all serialization and validation.
- **Dependency injection** in the style of FastAPI, with `Depends(...)`.
- **Built-in testing**: run tasks in-process with `TestApp`, in drain or eager mode.
- **Redis and RabbitMQ** brokers, plus an in-memory broker for local development.
- **Cron scheduling** and **multi-process workers** from one CLI.

Next: [Getting started](getting-started.md).
