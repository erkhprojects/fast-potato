# Tasks & type safety

## A task with input

The first parameter is the task's **input**, a Pydantic model. It's the only
thing you pass to `send()`.

```python
class Order(BaseModel):
    order_id: int
    items: list[str]


@app.task
async def process(order: Order) -> int:
    return len(order.items)


await process.send(Order(order_id=1, items=["book", "pen"]))
```

## A task without input

```python
@app.task
async def heartbeat() -> None: ...


await heartbeat.send()
```

## Send options

```python
from datetime import UTC, datetime

await process.send(order, delay=30)                                # run in 30 seconds
await process.send(order, eta=datetime(2030, 1, 1, tzinfo=UTC))    # run at a time
await process.send(order, queue="priority")                        # override the queue


@app.task(queue="emails")                                          # default queue for a task
async def send_email(order: Order) -> None: ...
```

`delay` and `eta` are mutually exclusive.

## What mypy checks

```python
await process.send(order)                   # ✅
await heartbeat.send()                      # ✅

await process.send()                        # ❌ missing input
await process.send({"order_id": 1})         # ❌ a dict is not an Order
await process.send(OtherModel(...))         # ❌ wrong model
await heartbeat.send(order)                 # ❌ task takes no input
```

!!! note
    For dependencies, use the `Annotated[...]` form (see
    [Dependency injection](dependencies.md)) so mypy understands the
    signature.

## Signature rules

Checked when `@app.task` runs, so mistakes fail at import time:

| Rule | Example that fails |
|---|---|
| Must be `async def` | `def process(order: Order)` |
| The first parameter is a Pydantic model, or the task takes no input | `async def process(order_id: int)` |
| Every other parameter is a dependency | `async def process(order: Order, retry: int)` |
| The input has no default and isn't optional | `order: Optional[Order]` |
| A `Potato` can't be the input (it's injected) | `async def reload(config: AppConfig)` |

At send time the data must be **exactly** the declared model. A subclass is
rejected, because its extra fields would be silently dropped.

## Custom field types

Serialization is Pydantic's job. Teach Pydantic about a type once and use it
in any input model:

```python
from typing import Annotated

from pydantic import BaseModel, PlainSerializer, PlainValidator


class Point:
    def __init__(self, x: float, y: float) -> None:
        self.x, self.y = x, y


def parse_point(value: object) -> Point:
    if isinstance(value, Point):
        return value
    x, y = str(value).split(",")
    return Point(float(x), float(y))


PointField = Annotated[
    Point,
    PlainValidator(parse_point),
    PlainSerializer(lambda p: f"{p.x},{p.y}", return_type=str),
]


class Line(BaseModel):
    start: PointField
    end: PointField
```

Tagged unions work too: `channel: Email | Sms = Field(discriminator="kind")`.

## On the wire

```python
msg = await process.send(Order(order_id=1, items=["book"]))
msg.payload  # {"order_id": 1, "items": ["book"]}
```

The worker rebuilds the input with `Order.model_validate(msg.payload)`.
