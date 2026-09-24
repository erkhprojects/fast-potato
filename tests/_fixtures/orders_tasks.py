from pydantic import BaseModel

from tests._fixtures import shared_app


class OrderInput(BaseModel):
    order_id: int


@shared_app.fixture_app.task(queue="orders")
async def process_order(data: OrderInput) -> None: ...


@shared_app.fixture_app.task(queue="orders")
async def cancel_order(data: OrderInput) -> None: ...
