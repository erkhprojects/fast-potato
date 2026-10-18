# Tâches et typage sûr

## Une tâche avec entrée

Le premier paramètre est l'**entrée** de la tâche, un modèle Pydantic. C'est la seule
chose que vous passez à `send()`.

```python
class Order(BaseModel):
    order_id: int
    items: list[str]


@app.task
async def process(order: Order) -> int:
    return len(order.items)


await process.send(Order(order_id=1, items=["book", "pen"]))
```

## Une tâche sans entrée

```python
@app.task
async def heartbeat() -> None: ...


await heartbeat.send()
```

## Options d'envoi

```python
from datetime import UTC, datetime

await process.send(order, delay=30)  # run in 30 seconds
await process.send(order, eta=datetime(2030, 1, 1, tzinfo=UTC))  # run at a time
await process.send(order, queue="priority")  # override the queue


@app.task(queue="emails")  # default queue for a task
async def send_email(order: Order) -> None: ...
```

`delay` et `eta` s'excluent mutuellement.

## Ce que mypy vérifie

```python
await process.send(order)  # ✅
await heartbeat.send()  # ✅

await process.send()  # ❌ missing input
await process.send({"order_id": 1})  # ❌ a dict is not an Order
await process.send(OtherModel(...))  # ❌ wrong model
await heartbeat.send(order)  # ❌ task takes no input
```

!!! note
    Pour les dépendances, utilisez la forme `Annotated[...]` (voir
    [Injection de dépendances](dependencies.md)) afin que mypy comprenne la
    signature.

## Règles de signature

Vérifiées lorsque `@app.task` s'exécute, de sorte que les erreurs échouent dès l'import :

| Règle | Exemple qui échoue |
|---|---|
| Doit être `async def` | `def process(order: Order)` |
| Le premier paramètre est un modèle Pydantic, ou la tâche ne prend pas d'entrée | `async def process(order_id: int)` |
| Tout autre paramètre est une dépendance | `async def process(order: Order, retry: int)` |
| L'entrée n'a pas de valeur par défaut et n'est pas optionnelle | `order: Optional[Order]` |
| Un `Potato` ne peut pas être l'entrée (il est injecté) | `async def reload(config: AppConfig)` |

Au moment de l'envoi, les données doivent être **exactement** le modèle déclaré. Une sous-classe est
rejetée, car ses champs supplémentaires seraient silencieusement ignorés.

## Types de champs personnalisés

La sérialisation est le travail de Pydantic. Apprenez un type à Pydantic une seule fois et utilisez-le
dans n'importe quel modèle d'entrée :

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

Les unions étiquetées fonctionnent aussi : `channel: Email | Sms = Field(discriminator="kind")`.

## Sur le réseau

```python
msg = await process.send(Order(order_id=1, items=["book"]))
msg.payload  # {"order_id": 1, "items": ["book"]}
```

Le worker reconstruit l'entrée avec `Order.model_validate(msg.payload)`.
