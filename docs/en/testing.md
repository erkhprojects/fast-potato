# Testing

`TestApp` runs your tasks in-process through the same code path as a real
worker: a JSON round-trip, Pydantic validation and dependency injection. On
exit it restores the app's broker, potato and dependency overrides.

## Drain mode (default)

`send()` only queues. `drain()` runs everything in order, including tasks sent
by other tasks.

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

## Eager mode

Every `send()` runs the task before it returns, anywhere in your code:

```python
with TestApp(app, eager=True) as t:
    await checkout(order)            # the whole chain has already run
    assert t.pending == []
```

## Running one task: `call()`

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

## Errors

A failing task raises in your test by default. To collect errors instead:

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

A complete example project is in `examples/testing/`.

## Cheat sheet

| | |
|---|---|
| `t.messages` | every message sent |
| `t.pending` | queued, not yet run |
| `t.runs` / `t.errors` | executions and their results or errors |
| `t.sent(task)` | decoded inputs sent to `task` |
| `t.assert_sent(task, data)` / `t.assert_not_sent(task)` | assertions |

!!! note
    `TestApp` modifies the shared `app`, so tests using it shouldn't run at
    the same time in one process. pytest-xdist (separate processes) is fine.
