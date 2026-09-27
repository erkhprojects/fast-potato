# Primeros pasos

## Instalación

Requiere Python 3.14+.

```bash
pip install "fast-potato[redis]"      # or [rabbitmq], or [all]
```

## 1. Define una app y una tarea

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

## 2. Envíala

```python
# anywhere in your application
from shop import Order, app, send_receipt


async def checkout() -> None:
    msg = await send_receipt.send(Order(order_id=1, email="alice@example.com"))
    print(msg.id, msg.payload)  # payload == {"order_id": 1, "email": "alice@example.com"}
```

## 3. Ejecuta un worker

```bash
fast-potato -A shop:app
```

El worker toma el mensaje de la cola `default` y ejecuta `send_receipt`.

!!! tip "¿No tienes Redis a mano?"
    Usa `MemoryBroker` de `fast_potato.brokers` para probar las cosas en un solo
    proceso, y consulta [Pruebas](testing.md) para ejecutar tareas en los tests.
