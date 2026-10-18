# Brokers

```python
from fast_potato.brokers import MemoryBroker, RabbitMQBroker, RedisBroker

RedisBroker("redis://localhost:6379/0")  # pip install "fast-potato[redis]"
RabbitMQBroker(
    "amqp://guest:guest@localhost:5672/"
)  # pip install "fast-potato[rabbitmq]"
MemoryBroker()  # in-process, no dependencies
```

| Broker | Retrasos (`delay` / `eta`) | Uso |
|---|---|---|
| `RedisBroker` | sorted set, revisado cada `poll_interval` (por defecto 1s) | producción |
| `RabbitMQBroker` | cola de retraso por cola usando el TTL de los mensajes | producción |
| `MemoryBroker` | **ignorados**: se ejecuta de inmediato | experimentos locales |

## Conexión

`send()` conecta el broker la primera vez que se usa, así que no hay nada que
configurar. Si el broker no responde dentro de `connect_timeout` (5 segundos
por defecto), `send()` lanza `BrokerConnectionError` en lugar de quedarse
bloqueado:

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

Las contraseñas de la URL se ocultan en el mensaje.

Con la conexión diferida, un problema de conexión solo aparece en tiempo de
ejecución, en el primer `send()`. Para que falle al arrancar, conéctate
manualmente. Esto además cierra la conexión limpiamente al apagar:

```python
async with app.broker:  # e.g. in your web framework's startup/lifespan hook
    ...
```

Los workers y el programador siempre se conectan al arrancar, y terminan con
`BrokerConnectionError` si el broker no es accesible.

## Escribir un broker

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
