from pydantic import BaseModel

from tests._fixtures import shared_app


class WelcomeInput(BaseModel):
    user_id: int


@shared_app.fixture_app.task(queue="emails")
async def send_welcome(data: WelcomeInput) -> None: ...
