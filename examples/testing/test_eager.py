"""
Eager mode: every send() runs the task immediately, before send() returns.
Handy for "call this, check the result" tests; nested sends run depth-first.
"""

import pytest
from conftest import FakeDatabase, FakeMailer
from shop import Order, Receipt, checkout, place_order, send_receipt, send_survey

from fast_potato.testing import TestApp

ORDER = Order(order_id=1, email="alice@example.com", amount_cents=4200)


async def test_checkout_runs_everything_immediately(
    potato_eager: TestApp, db: FakeDatabase, mailer: FakeMailer
) -> None:
    await checkout(ORDER)

    # No drain() needed: the whole chain already ran, delays are ignored.
    assert db.orders == [ORDER]
    assert [to for to, _ in mailer.outbox] == ["alice@example.com"] * 2
    assert potato_eager.pending == []


async def test_messages_are_still_recorded(potato_eager: TestApp) -> None:
    await checkout(ORDER)

    potato_eager.assert_sent(place_order, ORDER)
    potato_eager.assert_sent(
        send_receipt, Receipt(order_id=1, email="alice@example.com")
    )
    # Runs are recorded as tasks finish: nested sends finish before their parent.
    assert [r.msg.task_name for r in potato_eager.runs] == [
        send_receipt.name,
        send_survey.name,
        place_order.name,
    ]


async def test_failure_raises_from_send(
    potato_eager: TestApp, mailer: FakeMailer
) -> None:
    with pytest.raises(ValueError, match="amount must be positive"):
        await checkout(Order(order_id=2, email="bob@example.com", amount_cents=0))
    assert mailer.outbox == []
