# Premiers pas

## Installation

Nécessite Python 3.14+.

```bash
pip install "fast-potato[redis]"      # or [rabbitmq], or [all]
```

## 1. Définir une app et une tâche

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

## 2. L'envoyer

```python
# anywhere in your application
from shop import Order, app, send_receipt


async def checkout() -> None:
    msg = await send_receipt.send(Order(order_id=1, email="alice@example.com"))
    print(
        msg.id, msg.payload
    )  # payload == {"order_id": 1, "email": "alice@example.com"}
```

## 3. Lancer un worker

```bash
fast-potato -A shop:app
```

Le worker récupère le message dans la file d'attente `default` et exécute `send_receipt`.

!!! tip "Pas de Redis sous la main ?"
    Utilisez `MemoryBroker` de `fast_potato.brokers` pour faire des essais dans un seul
    processus, et consultez [Tests](testing.md) pour exécuter des tâches dans des tests.
