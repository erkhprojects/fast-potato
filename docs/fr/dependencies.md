# Injection de dépendances

Chaque paramètre qui suit l'entrée est injecté par le worker. Les appelants ne les passent jamais
à `send()`.

## `Depends`

```python
from typing import Annotated

from fast_potato import Depends


def get_settings() -> Settings:
    return Settings()


@app.task
async def process(
    order: Order,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None: ...


await process.send(Order(order_id=1))  # settings is resolved on the worker
```

Une dépendance peut être une fonction synchrone ou asynchrone, ou une classe. Les paramètres
de `__init__` d'une classe peuvent aussi être des dépendances. Avec un simple `Depends()`, le
type de l'annotation est utilisé comme dépendance :

```python
class PaymentGateway:
    def __init__(self, settings: Annotated[Settings, Depends(get_settings)]) -> None:
        self.settings = settings


@app.task
async def charge(order: Order, gateway: Annotated[PaymentGateway, Depends()]) -> None: ...
```

Chaque dépendance est résolue **une fois par exécution de tâche** et partagée par tout
ce qui en a besoin pendant cette exécution.

## Initialisation et nettoyage avec `yield`

```python
async def get_db() -> AsyncIterator[Session]:
    session = await Session.open()
    try:
        yield session          # injected into the task
    finally:
        await session.close()  # runs after the task finishes


@app.task
async def save(order: Order, db: Annotated[Session, Depends(get_db)]) -> None: ...
```

## Configuration globale de l'app : `Potato`

Un `Potato` est un modèle Pydantic figé, créé une seule fois et injecté partout où il est
déclaré :

```python
from fast_potato import FastPotato, Potato


class AppConfig(Potato):
    currency: str = "EUR"


app = FastPotato("shop", broker=broker, potato=AppConfig(currency="USD"))


@app.task
async def invoice(order: Order, config: Annotated[AppConfig, Depends()]) -> str:
    return f"{order.order_id} in {config.currency}"
```

## Remplacer des dépendances

`app.dependency_overrides` remplace une dépendance par une autre, comme dans
FastAPI. C'est surtout utile pour les tests :

```python
app.dependency_overrides[get_db] = get_fake_db
```

L'injection de dépendances s'exécute toujours ; elle appelle simplement `get_fake_db` partout où
`Depends(get_db)` apparaît. Dans les tests, préférez `TestApp.override()`, qui annule
le remplacement automatiquement ([Tests](testing.md)).

!!! warning "Utilisez la forme `Annotated` pour la vérification des types"
    `db: Session = Depends(get_db)` et `config: AppConfig = Depends[AppConfig]`
    fonctionnent à l'exécution, mais mypy signale actuellement des erreurs pour ces formes. Écrivez
    plutôt `Annotated[Session, Depends(get_db)]` et `Annotated[AppConfig, Depends()]`.
