# Inyección de dependencias

Cada parámetro después de la entrada lo inyecta el worker. Quien llama nunca los
pasa a `send()`.

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

Una dependencia puede ser una función síncrona o asíncrona, o una clase. Los
parámetros del `__init__` de una clase también pueden ser dependencias. Con un `Depends()` sin argumentos, el
tipo de la anotación se usa como dependencia:

```python
class PaymentGateway:
    def __init__(self, settings: Annotated[Settings, Depends(get_settings)]) -> None:
        self.settings = settings


@app.task
async def charge(
    order: Order, gateway: Annotated[PaymentGateway, Depends()]
) -> None: ...
```

Cada dependencia se resuelve **una vez por ejecución de la tarea** y se comparte con todo
lo que la necesite durante esa ejecución.

## Preparación y limpieza con `yield`

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

## Configuración para toda la app: `Potato`

Un `Potato` es un modelo de Pydantic congelado que se crea una vez y se inyecta dondequiera que
se declare:

```python
from fast_potato import FastPotato, Potato


class AppConfig(Potato):
    currency: str = "EUR"


app = FastPotato("shop", broker=broker, potato=AppConfig(currency="USD"))


@app.task
async def invoice(order: Order, config: Annotated[AppConfig, Depends()]) -> str:
    return f"{order.order_id} in {config.currency}"
```

## Sobrescribir dependencias

`app.dependency_overrides` reemplaza una dependencia por otra, como en
FastAPI. Es principalmente para los tests:

```python
app.dependency_overrides[get_db] = get_fake_db
```

La inyección de dependencias sigue ejecutándose; simplemente llama a `get_fake_db` dondequiera que
aparezca `Depends(get_db)`. En los tests, prefiere `TestApp.override()`, que deshace
la sobrescritura automáticamente ([Pruebas](testing.md)).

!!! warning "Usa la forma `Annotated` para la comprobación de tipos"
    `db: Session = Depends(get_db)` y `config: AppConfig = Depends[AppConfig]`
    funcionan en tiempo de ejecución, pero actualmente mypy reporta errores en ellas. Escribe
    `Annotated[Session, Depends(get_db)]` y `Annotated[AppConfig, Depends()]`
    en su lugar.
