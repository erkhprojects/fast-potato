# Broker

```python
from fast_potato.brokers import MemoryBroker, RabbitMQBroker, RedisBroker

RedisBroker("redis://localhost:6379/0")  # pip install "fast-potato[redis]"
RabbitMQBroker(
    "amqp://guest:guest@localhost:5672/"
)  # pip install "fast-potato[rabbitmq]"
MemoryBroker()  # in-process, no dependencies
```

| Broker | Verzögerungen (`delay` / `eta`) | Einsatzzweck |
|---|---|---|
| `RedisBroker` | Sorted Set, geprüft alle `poll_interval` (Standard 1s) | Produktion |
| `RabbitMQBroker` | Delay-Queue pro Queue mittels Message-TTL | Produktion |
| `MemoryBroker` | **ignoriert**: läuft sofort | lokale Experimente |

## Verbinden

`send()` verbindet den Broker bei der ersten Verwendung, du musst also nichts
einrichten. Ist der Broker nicht innerhalb von `connect_timeout` (Standard:
5 Sekunden) erreichbar, wirft `send()` einen `BrokerConnectionError`, statt zu
hängen:

```python
from fast_potato.brokers import BrokerConnectionError, RedisBroker

broker = RedisBroker("redis://localhost:6379/0", connect_timeout=2)

try:
    await send_receipt.send(order)
except BrokerConnectionError as exc:
    print(
        exc
    )  # Could not connect to Redis at redis://localhost:6379/0 (timeout 2s): ...
```

Passwörter in der URL werden in der Meldung ausgeblendet.

Beim verzögerten Verbinden zeigt sich ein Verbindungsproblem erst zur Laufzeit,
beim ersten `send()`. Wenn es schon beim Start auffallen soll, verbinde
manuell. Das schließt die Verbindung beim Herunterfahren außerdem sauber:

```python
async with app.broker:  # e.g. in your web framework's startup/lifespan hook
    ...
```

Worker und Scheduler verbinden sich immer beim Start und beenden sich mit
`BrokerConnectionError`, wenn der Broker nicht erreichbar ist.

## Einen Broker schreiben

```python
from collections.abc import AsyncGenerator

from fast_potato import TaskMessage
from fast_potato.brokers import AbstractBroker


class MyBroker(AbstractBroker):
    @property
    def is_connected(self) -> bool: ...

    async def connect(self) -> None: ...  # raise BrokerConnectionError, don't hang
    async def disconnect(self) -> None: ...

    async def publish(
        self, msg: TaskMessage
    ) -> None: ...  # store msg.model_dump_json() on msg.queue; honor msg.eta

    async def consume(self, queues: list[str]) -> AsyncGenerator[TaskMessage]:
        while True:
            raw = ...  # wait for the next message from any of `queues`
            yield TaskMessage.model_validate_json(raw)
```
