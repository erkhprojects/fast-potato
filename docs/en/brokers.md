# Brokers

```python
from fast_potato.brokers import MemoryBroker, RabbitMQBroker, RedisBroker

RedisBroker("redis://localhost:6379/0")               # pip install "fast-potato[redis]"
RabbitMQBroker("amqp://guest:guest@localhost:5672/")  # pip install "fast-potato[rabbitmq]"
MemoryBroker()                                        # in-process, no dependencies
```

| Broker | Delays (`delay` / `eta`) | Use for |
|---|---|---|
| `RedisBroker` | sorted set, checked every `poll_interval` (default 1s) | production |
| `RabbitMQBroker` | per-queue delay queue using message TTL | production |
| `MemoryBroker` | **ignored**: runs immediately | local experiments |

## Connecting

`send()` connects the broker on first use, so there's nothing to set up. If the
broker can't be reached within `connect_timeout` (default 5 seconds), `send()`
raises `BrokerConnectionError` instead of hanging:

```python
from fast_potato.brokers import BrokerConnectionError, RedisBroker

broker = RedisBroker("redis://localhost:6379/0", connect_timeout=2)

try:
    await send_receipt.send(order)
except BrokerConnectionError as exc:
    print(exc)  # Could not connect to Redis at redis://localhost:6379/0 (timeout 2s): ...
```

Passwords in the URL are hidden in the message.

With lazy connecting, a connection problem only surfaces at runtime, on the
first `send()`. To fail at startup instead, connect manually. This also closes
the connection cleanly on shutdown:

```python
async with app.broker:  # e.g. in your web framework's startup/lifespan hook
    ...
```

Workers and the scheduler always connect at startup, and exit with
`BrokerConnectionError` if the broker is unreachable.

## Writing a broker

```python
from collections.abc import AsyncGenerator

from fast_potato import TaskMessage
from fast_potato.brokers import AbstractBroker


class MyBroker(AbstractBroker):
    @property
    def is_connected(self) -> bool: ...

    async def connect(self) -> None: ...  # raise BrokerConnectionError, don't hang
    async def disconnect(self) -> None: ...

    async def publish(self, msg: TaskMessage) -> None:
        ...  # store msg.model_dump_json() on msg.queue; honor msg.eta

    async def consume(self, queues: list[str]) -> AsyncGenerator[TaskMessage]:
        while True:
            raw = ...  # wait for the next message from any of `queues`
            yield TaskMessage.model_validate_json(raw)
```
