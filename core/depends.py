from __future__ import annotations

from collections.abc import Callable
from typing import Any


class Depends:
    """
    Declare a dependency on a callable.

    Usage:
        async def get_db() -> AsyncGenerator[Database, None]:
            db = Database()
            yield db
            await db.close()

        @app.task
        async def my_task(order_id: int, db: Database = Depends(get_db)):
            ...
    """

    def __init__(self, dependency: Callable[..., Any]) -> None:
        self.dependency = dependency

    def __repr__(self) -> str:
        return f"Depends({self.dependency.__qualname__})"
