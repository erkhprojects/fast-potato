from __future__ import annotations

from collections.abc import Callable
from typing import Any


class _BaseDependency:
    """Marker base for all dependency descriptors used as parameter defaults."""


class Depends(_BaseDependency):
    """
    Declare a callable dependency.

    Usage:
        async def get_db() -> AsyncGenerator[Database, None]:
            db = Database()
            yield db
            await db.close()

        @app.task
        async def my_task(order_id: int, db: Database = Depends(get_db)):
            ...

    For app-level singletons (subclasses of Potato) use the subscript form:

        @app.task
        async def my_task(config: MyConfig = Depends[MyConfig]):
            ...
    """

    def __init__(self, dependency: Callable[..., Any]) -> None:
        self.dependency = dependency

    def __class_getitem__(cls, potato_type: type) -> PotatoDepends:
        return PotatoDepends(potato_type)

    def __repr__(self) -> str:
        return f"Depends({self.dependency.__qualname__})"


class PotatoDepends(_BaseDependency):
    """
    Declare a dependency on the app-level Potato singleton.
    Created via the Depends[SomePotatoSubclass] subscript syntax.
    """

    def __init__(self, potato_type: type) -> None:
        self.potato_type = potato_type

    def __repr__(self) -> str:
        return f"Depends[{self.potato_type.__name__}]"
