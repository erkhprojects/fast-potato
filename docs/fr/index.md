---
title: fast-potato
---

![fast-potato](../assets/logo.svg#only-light){ width="420" }
![fast-potato](../assets/logo-dark.svg#only-dark){ width="420" }

Une file d'attente de tâches distribuée pour Python, pensée d'abord pour l'asynchrone, construite sur `asyncio` et Pydantic.

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

## Typage sûr par conception

Chaque tâche prend un modèle Pydantic comme entrée, et `send()` est entièrement typé.
mypy (ou pyright) détecte les données incorrectes ou manquantes avant l'exécution de votre code :

```python
await send_receipt.send({"order_id": 1})
# error: Argument 1 to "send" of "Task" has incompatible type "dict[str, int]"; expected "Order"

await send_receipt.send()
# error: Missing positional argument "data" in call to "send" of "Task"
```

## Fonctionnalités

- **Pydantic en entrée, Pydantic en sortie** : Pydantic gère toute la sérialisation et la validation.
- **Injection de dépendances** dans le style de FastAPI, avec `Depends(...)`.
- **Tests intégrés** : exécutez les tâches dans le processus avec `TestApp`, en mode drain ou en mode eager.
- Brokers **Redis et RabbitMQ**, ainsi qu'un broker en mémoire pour le développement local.
- **Planification cron** et **workers multi-processus** depuis une seule CLI.

Suite : [Premiers pas](getting-started.md).
