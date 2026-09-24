"""
Shared fixtures for the testing examples.

Run with:
    uv run pytest examples/testing
"""

from collections.abc import Iterator

import pytest
import shop

from fast_potato.testing import TestApp


class FakeDatabase(shop.Database):
    def __init__(self) -> None:
        super().__init__(dsn="memory://")
        self.orders: list[shop.Order] = []

    def save(self, order: shop.Order) -> None:
        self.orders.append(order)

    def delete_stale_orders(self) -> int:
        removed = len(self.orders)
        self.orders.clear()
        return removed


class FakeMailer(shop.Mailer):
    def __init__(self) -> None:
        super().__init__(host="memory://")
        self.outbox: list[tuple[str, str]] = []

    async def send(self, to: str, body: str) -> None:
        self.outbox.append((to, body))


@pytest.fixture
def db() -> FakeDatabase:
    return FakeDatabase()


@pytest.fixture
def mailer() -> FakeMailer:
    return FakeMailer()


def _use_fakes(t: TestApp, db: FakeDatabase, mailer: FakeMailer) -> None:
    # Keys are the exact functions used in Depends(...); dependency injection
    # still runs, it just calls these instead.
    t.override(shop.get_db, lambda: db)
    t.override(shop.get_mailer, lambda: mailer)


@pytest.fixture
def potato(db: FakeDatabase, mailer: FakeMailer) -> Iterator[TestApp]:
    """Drain mode: send() only queues; call `await potato.drain()` to run."""
    with TestApp(shop.app) as t:
        _use_fakes(t, db, mailer)
        yield t
    # Leaving the block restores the app's broker, potato and overrides.


@pytest.fixture
def potato_eager(db: FakeDatabase, mailer: FakeMailer) -> Iterator[TestApp]:
    """Eager mode: every send() runs the task before it returns."""
    with TestApp(shop.app, eager=True) as t:
        _use_fakes(t, db, mailer)
        yield t
