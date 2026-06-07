from core.tests._fixtures.shared_app import fixture_app


@fixture_app.task(queue="orders")
async def process_order(order_id: int) -> None: ...


@fixture_app.task(queue="orders")
async def cancel_order(order_id: int) -> None: ...
