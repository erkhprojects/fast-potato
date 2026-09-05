from tests._fixtures import shared_app


@shared_app.fixture_app.task(queue="orders")
async def process_order(order_id: int) -> None: ...


@shared_app.fixture_app.task(queue="orders")
async def cancel_order(order_id: int) -> None: ...
