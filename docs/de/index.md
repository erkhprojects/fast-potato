# fast-potato

Eine async-first verteilte Task-Queue für Python, gebaut auf `asyncio` und Pydantic.

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

## Typsicher von Grund auf

Jede Task nimmt ein Pydantic-Modell als Eingabe, und `send()` ist vollständig typisiert.
mypy (oder pyright) erkennt falsche oder fehlende Daten, bevor dein Code läuft:

```python
await send_receipt.send({"order_id": 1})
# error: Argument 1 to "send" of "Task" has incompatible type "dict[str, int]"; expected "Order"

await send_receipt.send()
# error: Missing positional argument "data" in call to "send" of "Task"
```

## Features

- **Pydantic rein, Pydantic raus**: Pydantic übernimmt die gesamte Serialisierung und Validierung.
- **Dependency Injection** im Stil von FastAPI, mit `Depends(...)`.
- **Eingebautes Testen**: Führe Tasks im selben Prozess mit `TestApp` aus, im Drain- oder Eager-Modus.
- **Redis- und RabbitMQ**-Broker, plus ein In-Memory-Broker für die lokale Entwicklung.
- **Cron-Zeitplanung** und **Multi-Prozess-Worker** über eine einzige CLI.

Weiter: [Erste Schritte](getting-started.md).
