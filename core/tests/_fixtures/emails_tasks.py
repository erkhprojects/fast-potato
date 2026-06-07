from core.tests._fixtures.shared_app import fixture_app


@fixture_app.task(queue="emails")
async def send_welcome(user_id: int) -> None: ...
