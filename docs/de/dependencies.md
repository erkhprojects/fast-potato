# Dependency Injection

Jeder Parameter nach der Eingabe wird vom Worker injiziert. Aufrufer übergeben
sie nie an `send()`.

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

Eine Abhängigkeit kann eine synchrone oder asynchrone Funktion oder eine Klasse sein. Auch die
`__init__`-Parameter einer Klasse können Abhängigkeiten sein. Mit einem bloßen `Depends()` wird
der Typ der Annotation als Abhängigkeit verwendet:

```python
class PaymentGateway:
    def __init__(self, settings: Annotated[Settings, Depends(get_settings)]) -> None:
        self.settings = settings


@app.task
async def charge(
    order: Order, gateway: Annotated[PaymentGateway, Depends()]
) -> None: ...
```

Jede Abhängigkeit wird **einmal pro Task-Ausführung** aufgelöst und von allem gemeinsam genutzt,
was sie während dieser Ausführung benötigt.

## Setup und Teardown mit `yield`

```python
async def get_db() -> AsyncIterator[Session]:
    session = await Session.open()
    try:
        yield session  # injected into the task
    finally:
        await session.close()  # runs after the task finishes


@app.task
async def save(order: Order, db: Annotated[Session, Depends(get_db)]) -> None: ...
```

## App-weite Konfiguration: `Potato`

Ein `Potato` ist ein eingefrorenes Pydantic-Modell, das einmal erstellt und überall dort injiziert wird,
wo es deklariert ist:

```python
from fast_potato import FastPotato, Potato


class AppConfig(Potato):
    currency: str = "EUR"


app = FastPotato("shop", broker=broker, potato=AppConfig(currency="USD"))


@app.task
async def invoice(order: Order, config: Annotated[AppConfig, Depends()]) -> str:
    return f"{order.order_id} in {config.currency}"
```

## Abhängigkeiten überschreiben

`app.dependency_overrides` tauscht eine Abhängigkeit gegen eine andere aus, wie in
FastAPI. Das ist hauptsächlich für Tests gedacht:

```python
app.dependency_overrides[get_db] = get_fake_db
```

Die Dependency Injection läuft weiterhin; sie ruft einfach `get_fake_db` überall dort auf, wo
`Depends(get_db)` vorkommt. Bevorzuge in Tests `TestApp.override()`, das die
Überschreibung automatisch rückgängig macht ([Testen](testing.md)).

!!! warning "Verwende die `Annotated`-Form für die Typprüfung"
    `db: Session = Depends(get_db)` und `config: AppConfig = Depends[AppConfig]`
    funktionieren zur Laufzeit, aber mypy meldet dafür derzeit Fehler. Schreib
    stattdessen `Annotated[Session, Depends(get_db)]` und `Annotated[AppConfig, Depends()]`.
