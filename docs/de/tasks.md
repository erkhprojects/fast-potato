# Tasks & Typsicherheit

## Eine Task mit Eingabe

Der erste Parameter ist die **Eingabe** der Task, ein Pydantic-Modell. Sie ist das Einzige,
was du an `send()` übergibst.

```python
class Order(BaseModel):
    order_id: int
    items: list[str]


@app.task
async def process(order: Order) -> int:
    return len(order.items)


await process.send(Order(order_id=1, items=["book", "pen"]))
```

## Eine Task ohne Eingabe

```python
@app.task
async def heartbeat() -> None: ...


await heartbeat.send()
```

## Sendeoptionen

```python
from datetime import UTC, datetime

await process.send(order, delay=30)                                # run in 30 seconds
await process.send(order, eta=datetime(2030, 1, 1, tzinfo=UTC))    # run at a time
await process.send(order, queue="priority")                        # override the queue


@app.task(queue="emails")                                          # default queue for a task
async def send_email(order: Order) -> None: ...
```

`delay` und `eta` schließen sich gegenseitig aus.

## Was mypy prüft

```python
await process.send(order)                   # ✅
await heartbeat.send()                      # ✅

await process.send()                        # ❌ missing input
await process.send({"order_id": 1})         # ❌ a dict is not an Order
await process.send(OtherModel(...))         # ❌ wrong model
await heartbeat.send(order)                 # ❌ task takes no input
```

!!! note
    Verwende für Abhängigkeiten die Form `Annotated[...]` (siehe
    [Dependency Injection](dependencies.md)), damit mypy die
    Signatur versteht.

## Regeln für Signaturen

Geprüft, wenn `@app.task` ausgeführt wird, sodass Fehler schon beim Import auffallen:

| Regel | Beispiel, das fehlschlägt |
|---|---|
| Muss `async def` sein | `def process(order: Order)` |
| Der erste Parameter ist ein Pydantic-Modell, oder die Task nimmt keine Eingabe | `async def process(order_id: int)` |
| Jeder weitere Parameter ist eine Abhängigkeit | `async def process(order: Order, retry: int)` |
| Die Eingabe hat keinen Default-Wert und ist nicht optional | `order: Optional[Order]` |
| Ein `Potato` kann nicht die Eingabe sein (er wird injiziert) | `async def reload(config: AppConfig)` |

Beim Senden müssen die Daten **exakt** das deklarierte Modell sein. Eine Unterklasse wird
abgelehnt, weil ihre zusätzlichen Felder stillschweigend verworfen würden.

## Eigene Feldtypen

Serialisierung ist Aufgabe von Pydantic. Bring Pydantic einen Typ einmal bei und verwende ihn
in jedem Eingabemodell:

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

Tagged Unions funktionieren ebenfalls: `channel: Email | Sms = Field(discriminator="kind")`.

## Auf der Leitung

```python
msg = await process.send(Order(order_id=1, items=["book"]))
msg.payload  # {"order_id": 1, "items": ["book"]}
```

Der Worker baut die Eingabe mit `Order.model_validate(msg.payload)` wieder auf.
