# Testen

`TestApp` führt deine Tasks im selben Prozess über denselben Codepfad aus wie ein echter
Worker: ein JSON-Roundtrip, Pydantic-Validierung und Dependency Injection. Beim
Verlassen stellt es Broker, Potato und Dependency-Overrides der App wieder her.

## Drain-Modus (Standard)

`send()` stellt nur in die Queue. `drain()` führt alles der Reihe nach aus, einschließlich Tasks, die
von anderen Tasks gesendet wurden.

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
await t.drain(queues=["orders"])     # only these queues
await t.drain(run_delayed=False)     # leave delay/eta tasks in t.pending
```

## Eager-Modus

Jedes `send()` führt die Task aus, bevor es zurückkehrt, überall in deinem Code:

```python
with TestApp(app, eager=True) as t:
    await checkout(order)            # the whole chain has already run
    assert t.pending == []
```

## Eine einzelne Task ausführen: `call()`

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

## Fehler

Eine fehlschlagende Task wirft standardmäßig eine Exception in deinem Test. Um Fehler stattdessen zu sammeln:

```python
with TestApp(app, raise_errors=False) as t:
    await boom.send()
    await t.drain()
    assert [type(r.error) for r in t.errors] == [ValueError]
```

## Fixtures in `conftest.py`

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

Ein vollständiges Beispielprojekt findest du in `examples/testing/`.

## Spickzettel

| | |
|---|---|
| `t.messages` | jede gesendete Nachricht |
| `t.pending` | in der Queue, noch nicht ausgeführt |
| `t.runs` / `t.errors` | Ausführungen und ihre Ergebnisse oder Fehler |
| `t.sent(task)` | dekodierte Eingaben, die an `task` gesendet wurden |
| `t.assert_sent(task, data)` / `t.assert_not_sent(task)` | Assertions |

!!! note
    `TestApp` verändert die gemeinsam genutzte `app`, daher sollten Tests, die es verwenden, nicht
    gleichzeitig in einem Prozess laufen. pytest-xdist (separate Prozesse) ist in Ordnung.
