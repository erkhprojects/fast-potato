# Tareas y seguridad de tipos

## Una tarea con entrada

El primer parámetro es la **entrada** de la tarea, un modelo de Pydantic. Es lo
único que le pasas a `send()`.

```python
class Order(BaseModel):
    order_id: int
    items: list[str]


@app.task
async def process(order: Order) -> int:
    return len(order.items)


await process.send(Order(order_id=1, items=["book", "pen"]))
```

## Una tarea sin entrada

```python
@app.task
async def heartbeat() -> None: ...


await heartbeat.send()
```

## Opciones de envío

```python
from datetime import UTC, datetime

await process.send(order, delay=30)  # run in 30 seconds
await process.send(order, eta=datetime(2030, 1, 1, tzinfo=UTC))  # run at a time
await process.send(order, queue="priority")  # override the queue


@app.task(queue="emails")  # default queue for a task
async def send_email(order: Order) -> None: ...
```

`delay` y `eta` son mutuamente excluyentes.

## Qué comprueba mypy

```python
await process.send(order)  # ✅
await heartbeat.send()  # ✅

await process.send()  # ❌ missing input
await process.send({"order_id": 1})  # ❌ a dict is not an Order
await process.send(OtherModel(...))  # ❌ wrong model
await heartbeat.send(order)  # ❌ task takes no input
```

!!! note
    Para las dependencias, usa la forma `Annotated[...]` (consulta
    [Inyección de dependencias](dependencies.md)) para que mypy entienda la
    firma.

## Reglas de la firma

Se comprueban cuando se ejecuta `@app.task`, así que los errores fallan en el momento de la importación:

| Regla | Ejemplo que falla |
|---|---|
| Debe ser `async def` | `def process(order: Order)` |
| El primer parámetro es un modelo de Pydantic, o la tarea no recibe entrada | `async def process(order_id: int)` |
| Todos los demás parámetros son dependencias | `async def process(order: Order, retry: int)` |
| La entrada no tiene valor por defecto y no es opcional | `order: Optional[Order]` |
| Un `Potato` no puede ser la entrada (se inyecta) | `async def reload(config: AppConfig)` |

Al enviar, los datos deben ser **exactamente** el modelo declarado. Una subclase se
rechaza, porque sus campos adicionales se descartarían silenciosamente.

## Tipos de campo personalizados

La serialización es trabajo de Pydantic. Enséñale a Pydantic un tipo una vez y úsalo
en cualquier modelo de entrada:

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

Las uniones etiquetadas también funcionan: `channel: Email | Sms = Field(discriminator="kind")`.

## En la red

```python
msg = await process.send(Order(order_id=1, items=["book"]))
msg.payload  # {"order_id": 1, "items": ["book"]}
```

El worker reconstruye la entrada con `Order.model_validate(msg.payload)`.
