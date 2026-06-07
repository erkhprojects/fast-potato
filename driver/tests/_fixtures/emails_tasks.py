from driver.tests._fixtures import shared_app


@shared_app.fixture_app.task(queue="emails")
async def send_welcome(user_id: int) -> None: ...
