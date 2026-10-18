# Dependency injection

Every parameter after the input is injected by the worker. Callers never pass
them to `send()`.

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

A dependency can be a sync or async function or a class. A class's
`__init__` parameters can be dependencies too. With a bare `Depends()`, the
annotation's type is used as the dependency:

```python
class PaymentGateway:
    def __init__(self, settings: Annotated[Settings, Depends(get_settings)]) -> None:
        self.settings = settings


@app.task
async def charge(
    order: Order, gateway: Annotated[PaymentGateway, Depends()]
) -> None: ...
```

Each dependency is resolved **once per task run** and shared by everything
that needs it during that run.

## Setup and teardown with `yield`

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

## App-wide config: `Potato`

A `Potato` is a frozen Pydantic model created once and injected wherever it's
declared:

```python
from fast_potato import FastPotato, Potato


class AppConfig(Potato):
    currency: str = "EUR"


app = FastPotato("shop", broker=broker, potato=AppConfig(currency="USD"))


@app.task
async def invoice(order: Order, config: Annotated[AppConfig, Depends()]) -> str:
    return f"{order.order_id} in {config.currency}"
```

## Overriding dependencies

`app.dependency_overrides` swaps a dependency for another one, as in
FastAPI. It's mainly for tests:

```python
app.dependency_overrides[get_db] = get_fake_db
```

Dependency injection still runs; it just calls `get_fake_db` wherever
`Depends(get_db)` appears. In tests, prefer `TestApp.override()`, which undoes
the override automatically ([Testing](testing.md)).

!!! warning "Use the `Annotated` form for type checking"
    `db: Session = Depends(get_db)` and `config: AppConfig = Depends[AppConfig]`
    work at runtime, but mypy currently reports errors on them. Write
    `Annotated[Session, Depends(get_db)]` and `Annotated[AppConfig, Depends()]`
    instead.
