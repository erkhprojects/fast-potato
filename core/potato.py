from __future__ import annotations

from pydantic import BaseModel


class Potato(BaseModel):
    """
    Base class for app-level singleton dependencies.

    Subclass this to define shared config or resources that are initialized
    once when the app starts and injected into tasks via Depends[YourClass].

    Example:
        class AppConfig(Potato):
            db_url: str
            redis_url: str
            debug: bool = False

        app = FastPotato("my_app", potato=AppConfig(db_url="...", redis_url="..."))

        @app.task
        async def my_task(order_id: int, config: AppConfig = Depends[AppConfig]):
            print(config.db_url)

    Frozen by default — config should not change after the app starts.
    Override model_config if you genuinely need mutability.
    """

    model_config = {"frozen": True}
