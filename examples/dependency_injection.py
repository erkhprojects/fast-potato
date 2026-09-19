"""
Fast-Potato Dependency Injection Example.

Demonstrates:
1. Global application config singleton (subclassing Potato).
2. Generator dependencies (yield) with automatic teardown/cleanup.
3. Nested dependencies (Service -> Repository -> Database Session).
4. Annotated dependency typing (Annotated[T, Depends(...)]).
5. Running in-memory and executing via Worker.

Run with:
    uv run python examples/dependency_injection.py
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Annotated

from fast_potato import Depends, FastPotato, Potato, Worker
from fast_potato.brokers import MemoryBroker

# --- 1. App Configuration Singleton (Potato) ---


class AppConfig(Potato):
    environment: str = "production"
    db_pool_size: int = 20
    api_key: str = "super-secret-key"


# Initialize FastPotato with our config singleton
app = FastPotato("di_app", broker=MemoryBroker(), potato=AppConfig())


# --- 2. Database Session with Teardown (Generator Dependency) ---


class FakeDBSession:
    def __init__(self, session_id: int) -> None:
        self.session_id = session_id
        self.active = True

    def query(self, entity: str) -> str:
        return f"SELECT * FROM {entity} (session #{self.session_id})"

    def close(self) -> None:
        self.active = False


_session_counter = 0


async def get_db() -> AsyncGenerator[FakeDBSession]:
    """Yield a database session and ensure it is closed after task completes."""
    global _session_counter
    _session_counter += 1
    session = FakeDBSession(_session_counter)
    print(f"[DI] Opened DB session #{session.session_id}")
    try:
        yield session
    finally:
        session.close()
        print(f"[DI] Closed DB session #{session.session_id} (active={session.active})")


# --- 3. Nested Dependencies (Repository -> Session, Service -> Repository) ---


class OrderRepository:
    """Repository depending on DB session."""

    def __init__(self, db: Annotated[FakeDBSession, Depends(get_db)]) -> None:
        self.db = db

    def get_order_total(self, order_id: int) -> float:
        _ = self.db.query("orders")
        return 99.95


class PaymentGateway:
    """Gateway depending on app configuration singleton."""

    def __init__(self, config: Annotated[AppConfig, Depends]) -> None:
        self.env = config.environment
        self.key = config.api_key

    def charge(self, amount: float) -> str:
        return f"CHARGED ${amount:.2f} in [{self.env}]"


class CheckoutService:
    """Higher-level service depending on multiple nested dependencies."""

    def __init__(
        self,
        repo: Annotated[OrderRepository, Depends(OrderRepository)],
        gateway: Annotated[PaymentGateway, Depends(PaymentGateway)],
    ) -> None:
        self.repo = repo
        self.gateway = gateway

    def process_checkout(self, order_id: int) -> str:
        total = self.repo.get_order_total(order_id)
        status = self.gateway.charge(total)
        return f"Order #{order_id}: {status}"


# --- 4. Task with Injected Dependencies ---


@app.task
async def complete_order_task(
    order_id: int,
    service: Annotated[CheckoutService, Depends(CheckoutService)],
    config: Annotated[AppConfig, Depends],
) -> None:
    print(f"[TASK] Processing in environment: {config.environment}")
    result = service.process_checkout(order_id)
    print(f"[TASK] Result: {result}")


# --- 5. Execution Demo ---


async def main() -> None:
    print("=== Sending Task to Memory Broker ===")
    await complete_order_task.send(order_id=1001)

    print("\n=== Worker Executing Task with Recursive Dependency Injection ===")
    worker = Worker(app=app)
    worker_task = asyncio.create_task(worker.run())
    await asyncio.sleep(0.05)
    worker.stop()
    await worker_task
    print("\nWorker finished processing.")


if __name__ == "__main__":
    asyncio.run(main())
