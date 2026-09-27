# fast-potato

Una cola de tareas distribuida para Python, async desde el diseño, construida sobre `asyncio` y Pydantic.

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

## Con seguridad de tipos por diseño

Cada tarea recibe un modelo de Pydantic como entrada, y `send()` está completamente tipado.
mypy (o pyright) detecta datos incorrectos o faltantes antes de que tu código se ejecute:

```python
await send_receipt.send({"order_id": 1})
# error: Argument 1 to "send" of "Task" has incompatible type "dict[str, int]"; expected "Order"

await send_receipt.send()
# error: Missing positional argument "data" in call to "send" of "Task"
```

## Características

- **Pydantic de entrada, Pydantic de salida**: Pydantic se encarga de toda la serialización y validación.
- **Inyección de dependencias** al estilo de FastAPI, con `Depends(...)`.
- **Pruebas integradas**: ejecuta tareas en el mismo proceso con `TestApp`, en modo drain o modo eager.
- Brokers de **Redis y RabbitMQ**, además de un broker en memoria para el desarrollo local.
- **Programación con cron** y **workers multiproceso** desde una sola CLI.

Siguiente: [Primeros pasos](getting-started.md).
