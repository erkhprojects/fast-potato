"""
Fast-Potato Distributed Brokers Example (Redis & RabbitMQ).

Demonstrates:
1. Configuring RedisBroker and RabbitMQBroker.
2. Routing tasks to specific queues (e.g. 'critical', 'notifications', 'default').
3. Scheduling delayed/ETA tasks in a distributed environment.
4. Programmatic worker execution and CLI instructions for distributed deployments.

Run with (requires local Redis on 6379 or RabbitMQ on 5672, or start via `uv run poe services-up`):
    uv run python examples/distributed_brokers.py
"""

from __future__ import annotations

import asyncio
import os
from typing import Annotated

from pydantic import BaseModel

from fast_potato import Depends, FastPotato, Potato
from fast_potato.brokers.base import AbstractBroker
from fast_potato.brokers.redis import RedisBroker
from fast_potato.worker import Worker


class ClusterConfig(Potato):
    datacenter: str = "eu-central-1"


# Select broker based on environment or availability
# Redis: "redis://localhost:6379/0"
# RabbitMQ: "amqp://guest:guest@localhost:5672/"
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
broker: AbstractBroker = RedisBroker(url=redis_url, poll_interval=1.0)

app = FastPotato("distributed_app", broker=broker, potato=ClusterConfig())


# --- Task Input Models ---
# Only the input model travels over the broker, as JSON in TaskMessage.payload.


class Payment(BaseModel):
    payment_id: str
    amount: float


class SmsAlert(BaseModel):
    phone_number: str
    message: str


# --- Register Tasks on Different Queues ---


@app.task(queue="critical")
async def process_payment(
    payment: Payment, cluster: Annotated[ClusterConfig, Depends]
) -> None:
    print(
        f"[CRITICAL QUEUE] Processing payment {payment.payment_id} "
        f"for ${payment.amount:.2f} in {cluster.datacenter}"
    )


@app.task(queue="notifications")
async def send_sms_alert(alert: SmsAlert) -> None:
    print(f"[NOTIFICATIONS QUEUE] SMS to {alert.phone_number}: {alert.message}")


@app.task
async def sync_cache() -> None:
    print("[DEFAULT QUEUE] Cache synchronized.")


# --- Main ---


async def main() -> None:
    print("=== Distributed Broker Example ===")

    try:
        await broker.connect()
    except Exception as exc:
        print(f"Broker connection failed ({exc}).")
        print("Tip: Start local services first using:")
        print("    uv run poe services-up")
        return

    try:
        print("\n1. Enqueuing tasks across different queues:")
        msg1 = await process_payment.send(Payment(payment_id="pay_8892", amount=150.00))
        print(f"   Enqueued to 'critical': task={msg1.task_name} id={msg1.id}")

        msg2 = await send_sms_alert.send(
            SmsAlert(phone_number="+1234567890", message="System update completed.")
        )
        print(f"   Enqueued to 'notifications': task={msg2.task_name} id={msg2.id}")

        # Enqueue with delay
        msg3 = await sync_cache.send(delay=1)
        print(f"   Enqueued to 'default' with delay=1s: id={msg3.id}")

        print("\n2. Processing tasks with a prioritized multi-queue Worker:")
        # Worker listens to multiple queues in priority order
        worker = Worker(
            app=app,
            queues=["critical", "notifications", "default"],
            concurrency=2,
        )

        worker_task = asyncio.create_task(worker.run())
        # Let worker consume the ready and delayed messages
        await asyncio.sleep(2.5)
        worker.stop()
        await worker_task
        print("\nWorker processed tasks and stopped cleanly.")

        print("\n3. Distributed CLI Deployment:")
        print("   In production, workers are typically started via the CLI:")
        print(
            "   fast-potato -A examples.distributed_brokers:app -q critical,notifications -w 2 -c 4"
        )

    finally:
        await broker.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
