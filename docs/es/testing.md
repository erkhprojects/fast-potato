# Pruebas

`TestApp` ejecuta tus tareas en el mismo proceso a través del mismo camino de código que un
worker real: un viaje de ida y vuelta por JSON, validación de Pydantic e inyección de dependencias. Al
salir, restaura el broker, el potato y las sobrescrituras de dependencias de la app.

## Modo drain (por defecto)

`send()` solo encola. `drain()` ejecuta todo en orden, incluidas las tareas enviadas
por otras tareas.

```python
from fast_potato.testing import TestApp


async def test_checkout() -> None:
    with TestApp(app) as t:
        await checkout(Order(order_id=1, email="alice@example.com"))

        t.assert_sent(place_order, Order(order_id=1, email="alice@example.com"))
        runs = await t.drain()

    assert runs[0].msg.task_name == place_order.name
```

```python
await t.drain(queues=["orders"])  # only these queues
await t.drain(run_delayed=False)  # leave delay/eta tasks in t.pending
```

## Modo eager

Cada `send()` ejecuta la tarea antes de retornar, en cualquier parte de tu código:

```python
with TestApp(app, eager=True) as t:
    await checkout(order)  # the whole chain has already run
    assert t.pending == []
```

## Ejecutar una sola tarea: `call()`

```python
with TestApp(app) as t:
    total = await t.call(process, Order(order_id=1, items=["book"]))  # typed result
```

## Fakes

```python
with TestApp(app, potato=AppConfig(currency="USD")) as t:
    t.override(get_db, get_fake_db)
    ...
```

## Errores

Por defecto, una tarea que falla lanza la excepción en tu test. Para recopilar los errores en su lugar:

```python
with TestApp(app, raise_errors=False) as t:
    await boom.send()
    await t.drain()
    assert [type(r.error) for r in t.errors] == [ValueError]
```

## Fixtures en `conftest.py`

```python
from collections.abc import Iterator

import pytest

from fast_potato.testing import TestApp
from shop import app, get_db


@pytest.fixture
def potato() -> Iterator[TestApp]:
    with TestApp(app) as t:
        t.override(get_db, get_fake_db)
        yield t


@pytest.fixture
def potato_eager() -> Iterator[TestApp]:
    with TestApp(app, eager=True) as t:
        t.override(get_db, get_fake_db)
        yield t
```

Hay un proyecto de ejemplo completo en `examples/testing/`.

## Referencia rápida

| | |
|---|---|
| `t.messages` | todos los mensajes enviados |
| `t.pending` | encolados, aún no ejecutados |
| `t.runs` / `t.errors` | ejecuciones y sus resultados o errores |
| `t.sent(task)` | entradas decodificadas enviadas a `task` |
| `t.assert_sent(task, data)` / `t.assert_not_sent(task)` | aserciones |

!!! note
    `TestApp` modifica la `app` compartida, así que los tests que la usan no deberían ejecutarse
    al mismo tiempo en un mismo proceso. pytest-xdist (procesos separados) no tiene problema.
