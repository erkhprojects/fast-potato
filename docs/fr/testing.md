# Tests

`TestApp` exécute vos tâches dans le processus en suivant le même chemin de code qu'un vrai
worker : un aller-retour JSON, la validation Pydantic et l'injection de dépendances. À la
sortie, il restaure le broker, le potato et les remplacements de dépendances de l'app.

## Mode drain (par défaut)

`send()` se contente de mettre en file d'attente. `drain()` exécute tout dans l'ordre, y compris les tâches envoyées
par d'autres tâches.

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

## Mode eager

Chaque `send()` exécute la tâche avant de retourner, n'importe où dans votre code :

```python
with TestApp(app, eager=True) as t:
    await checkout(order)            # the whole chain has already run
    assert t.pending == []
```

## Exécuter une seule tâche : `call()`

```python
with TestApp(app) as t:
    total = await t.call(process, Order(order_id=1, items=["book"]))  # typed result
```

## Substituts

```python
with TestApp(app, potato=AppConfig(currency="USD")) as t:
    t.override(get_db, get_fake_db)
    ...
```

## Erreurs

Par défaut, une tâche qui échoue lève une exception dans votre test. Pour collecter les erreurs à la place :

```python
with TestApp(app, raise_errors=False) as t:
    await boom.send()
    await t.drain()
    assert [type(r.error) for r in t.errors] == [ValueError]
```

## Fixtures dans `conftest.py`

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

Un projet d'exemple complet se trouve dans `examples/testing/`.

## Aide-mémoire

| | |
|---|---|
| `t.messages` | tous les messages envoyés |
| `t.pending` | en file d'attente, pas encore exécutés |
| `t.runs` / `t.errors` | exécutions et leurs résultats ou erreurs |
| `t.sent(task)` | entrées décodées envoyées à `task` |
| `t.assert_sent(task, data)` / `t.assert_not_sent(task)` | assertions |

!!! note
    `TestApp` modifie l'`app` partagée, donc les tests qui l'utilisent ne doivent pas s'exécuter
    en même temps dans un même processus. pytest-xdist (processus séparés) convient.
