"""
A tiny shop app used by the testing examples.

Treat this module as "your project's tasks module". Its real dependencies
(a database and a mail server) are unavailable in tests, so the tests in this
folder replace them with fakes via TestApp.override().

Flow: checkout() -> place_order -> send_receipt, plus a delayed survey email.
"""

from typing import Annotated

from pydantic import BaseModel

from fast_potato import Depends, FastPotato, Potato
from fast_potato.brokers import MemoryBroker


class ShopConfig(Potato):
    currency: str = "EUR"


app = FastPotato("shop", broker=MemoryBroker(), potato=ShopConfig())


# --- Input models ---


class Order(BaseModel):
    order_id: int
    email: str
    amount_cents: int


class Receipt(BaseModel):
    order_id: int
    email: str


class Survey(BaseModel):
    email: str


# --- Real dependencies (need infrastructure) ---


class Database:
    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def save(self, order: Order) -> None:
        raise ConnectionError(f"no database reachable at {self.dsn}")

    def delete_stale_orders(self) -> int:
        raise ConnectionError(f"no database reachable at {self.dsn}")


class Mailer:
    def __init__(self, host: str) -> None:
        self.host = host

    async def send(self, to: str, body: str) -> None:
        raise ConnectionError(f"no mail server reachable at {self.host}")


def get_db() -> Database:
    return Database(dsn="postgresql://prod/shop")


def get_mailer() -> Mailer:
    return Mailer(host="smtp.example.com")


# --- Tasks ---


@app.task(queue="orders")
async def place_order(order: Order, db: Annotated[Database, Depends(get_db)]) -> None:
    if order.amount_cents <= 0:
        raise ValueError(f"order {order.order_id}: amount must be positive")
    db.save(order)
    await send_receipt.send(Receipt(order_id=order.order_id, email=order.email))
    await send_survey.send(Survey(email=order.email), delay=24 * 3600)


@app.task(queue="emails")
async def send_receipt(
    receipt: Receipt,
    mailer: Annotated[Mailer, Depends(get_mailer)],
    config: Annotated[ShopConfig, Depends()],
) -> str:
    body = f"Thanks for order #{receipt.order_id} (prices in {config.currency})"
    await mailer.send(receipt.email, body)
    return body


@app.task(queue="emails")
async def send_survey(
    survey: Survey, mailer: Annotated[Mailer, Depends(get_mailer)]
) -> None:
    await mailer.send(survey.email, "How was your order?")


@app.task
async def nightly_cleanup(db: Annotated[Database, Depends(get_db)]) -> int:
    return db.delete_stale_orders()


# --- Application code that enqueues work (e.g. a web handler) ---


async def checkout(order: Order) -> None:
    await place_order.send(order)
