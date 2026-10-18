# Erste Schritte

## Installation

Erfordert Python 3.14+.

```bash
pip install "fast-potato[redis]"      # or [rabbitmq], or [all]
```

## 1. Eine App und eine Task definieren

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
async def send_receipt(order: Order) -> str:
    return f"receipt for #{order.order_id} sent to {order.email}"
```

## 2. Sie senden

```python
# anywhere in your application
from shop import Order, app, send_receipt


async def checkout() -> None:
    msg = await send_receipt.send(Order(order_id=1, email="alice@example.com"))
    print(
        msg.id, msg.payload
    )  # payload == {"order_id": 1, "email": "alice@example.com"}
```

## 3. Einen Worker starten

```bash
fast-potato -A shop:app
```

Der Worker holt die Nachricht aus der Queue `default` ab und führt `send_receipt` aus.

!!! tip "Kein Redis zur Hand?"
    Verwende `MemoryBroker` aus `fast_potato.brokers`, um Dinge in einem einzigen
    Prozess auszuprobieren, und sieh dir [Testen](testing.md) an, um Tasks in Tests auszuführen.
