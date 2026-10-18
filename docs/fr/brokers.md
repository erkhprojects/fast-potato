# Brokers

```python
from fast_potato.brokers import MemoryBroker, RabbitMQBroker, RedisBroker

RedisBroker("redis://localhost:6379/0")  # pip install "fast-potato[redis]"
RabbitMQBroker(
    "amqp://guest:guest@localhost:5672/"
)  # pip install "fast-potato[rabbitmq]"
MemoryBroker()  # in-process, no dependencies
```

| Broker | Délais (`delay` / `eta`) | Utilisation |
|---|---|---|
| `RedisBroker` | ensemble trié, vérifié toutes les `poll_interval` (1s par défaut) | production |
| `RabbitMQBroker` | file de délai par file d'attente, via le TTL des messages | production |
| `MemoryBroker` | **ignorés** : exécution immédiate | expériences locales |

## Connexion

`send()` connecte le broker à la première utilisation : vous n'avez rien à
configurer. Si le broker est injoignable dans le délai `connect_timeout`
(5 secondes par défaut), `send()` lève `BrokerConnectionError` au lieu de
rester bloqué :

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

Les mots de passe présents dans l'URL sont masqués dans le message.

Avec la connexion paresseuse, un problème de connexion n'apparaît qu'à
l'exécution, au premier `send()`. Pour échouer dès le démarrage, connectez-vous
manuellement. Cela ferme aussi proprement la connexion à l'arrêt :

```python
async with app.broker:  # e.g. in your web framework's startup/lifespan hook
    ...
```

Les workers et le planificateur se connectent toujours au démarrage, et
s'arrêtent avec `BrokerConnectionError` si le broker est injoignable.

## Écrire un broker

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
