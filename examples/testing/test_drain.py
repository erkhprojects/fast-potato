"""
Drain mode: send() queues messages; drain() runs them in FIFO order through the
real worker code path (JSON round-trip, validation, dependency injection).
"""

import pytest
from conftest import FakeDatabase, FakeMailer
from shop import (
    Order,
    Receipt,
    ShopConfig,
    Survey,
    app,
    checkout,
    get_mailer,
    nightly_cleanup,
    place_order,
    send_receipt,
    send_survey,
)

from fast_potato.testing import TestApp

ORDER = Order(order_id=1, email="alice@example.com", amount_cents=4200)


async def test_checkout_only_queues(potato: TestApp) -> None:
    await checkout(ORDER)

    # Nothing has run yet: the message is waiting in the queue.
    potato.assert_sent(place_order, ORDER)
    assert [m.task_name for m in potato.pending] == [place_order.name]


async def test_drain_runs_the_whole_chain(
    potato: TestApp, db: FakeDatabase, mailer: FakeMailer
) -> None:
    await checkout(ORDER)
    runs = await potato.drain()

    # place_order ran, then the tasks it sent (the delayed survey included).
    assert [r.msg.task_name for r in runs] == [
        place_order.name,
        send_receipt.name,
        send_survey.name,
    ]
    assert db.orders == [ORDER]
    assert mailer.outbox[0] == (
        "alice@example.com",
        "Thanks for order #1 (prices in EUR)",
    )
    assert runs[1].result == "Thanks for order #1 (prices in EUR)"
    assert potato.pending == []


async def test_delayed_tasks_can_stay_queued(
    potato: TestApp, mailer: FakeMailer
) -> None:
    await checkout(ORDER)
    await potato.drain(run_delayed=False)

    # The survey is scheduled 24h ahead, so it is still waiting.
    potato.assert_sent(send_survey, Survey(email="alice@example.com"))
    assert [m.task_name for m in potato.pending] == [send_survey.name]
    assert len(mailer.outbox) == 1


async def test_drain_one_queue_at_a_time(potato: TestApp, db: FakeDatabase) -> None:
    await checkout(ORDER)
    await potato.drain(queues=["orders"])

    assert db.orders == [ORDER]
    potato.assert_sent(send_receipt, Receipt(order_id=1, email="alice@example.com"))
    assert {m.queue for m in potato.pending} == {"emails"}


async def test_failing_task_raises_into_the_test(potato: TestApp) -> None:
    await place_order.send(Order(order_id=2, email="bob@example.com", amount_cents=0))

    with pytest.raises(ValueError, match="amount must be positive"):
        await potato.drain()
    potato.assert_not_sent(send_receipt)


async def test_call_runs_one_task_directly(potato: TestApp, db: FakeDatabase) -> None:
    db.save(ORDER)

    # call() runs a task right away, with injection, and returns its result.
    assert await potato.call(nightly_cleanup) == 1
    assert db.orders == []


async def test_potato_can_be_swapped(mailer: FakeMailer) -> None:
    # Build a TestApp inline when a test needs a different setup.
    with TestApp(app, potato=ShopConfig(currency="USD")) as t:
        t.override(get_mailer, lambda: mailer)
        result = await t.call(send_receipt, Receipt(order_id=3, email="c@x.io"))
    assert result == "Thanks for order #3 (prices in USD)"
