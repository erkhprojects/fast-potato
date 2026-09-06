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

from fast_potato import FastPotato, Potato
from fast_potato.brokers.base import AbstractBroker
from fast_potato.brokers.rabbitmq import RabbitMQBroker
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


# --- Register Tasks on Different Queues ---


@app.task(queue="critical")
async def process_payment(payment_id: str, amount: float) -> None:
    print(f"[CRITICAL QUEUE] Processing payment {payment_id} for ${amount:.2f}")


@app.task(queue="notifications")
async def send_sms_alert(phone_number: str, message: str) -> None:
    print(f"[NOTIFICATIONS QUEUE] SMS to {phone_number}: {message}")


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
        msg1 = await process_payment.send("pay_8892", 150.00)
        print(f"   Enqueued to 'critical': task={msg1.task_name} id={msg1.id}")

        msg2 = await send_sms_alert.send("+1234567890", "System update completed.")
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

        # Let delayed task become ready
        await asyncio.sleep(1.2)

        processed = await worker.run_until_empty()
        print(f"\nWorker finished: {processed} task(s) processed across queues.")

        print("\n3. Distributed CLI Deployment:")
        print("   In production, workers are typically started via the CLI:")
        print(
            "   fast-potato -A examples.distributed_brokers:app -q critical -q notifications -w 2 -c 4"
        )

    finally:
        await broker.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
