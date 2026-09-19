"""
Fast-Potato Periodic & Scheduled Tasks Example.

Demonstrates:
1. Defining schedules using cron expressions and the `crontab()` helper.
2. Passing schedules to FastPotato app initialization.
3. Using the `Scheduler` to evaluate and dispatch due tasks.
4. Using the `Worker` to consume and process scheduled task runs.

Run with:
    uv run python examples/scheduled_tasks.py
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from fast_potato import FastPotato, Schedule, Scheduler, Worker, crontab
from fast_potato.brokers import MemoryBroker

broker = MemoryBroker()

# Initialize the application with cron schedules
app = FastPotato(
    "cron_app",
    broker=broker,
    schedules=[
        # Runs every hour at minute 0
        Schedule(
            task="cron_app.generate_hourly_report",
            cron="0 * * * *",
            queue="reports",
        ),
        # Runs every weekday at 09:00 AM with arguments
        Schedule(
            task="cron_app.send_daily_digest",
            cron=crontab(minute="0", hour="9", day_of_week="1-5"),
            queue="emails",
            kwargs={"include_analytics": True},
        ),
        # Runs every minute
        Schedule(
            task="cron_app.heartbeat_check",
            cron="* * * * *",
        ),
    ],
)


# --- Register Scheduled Tasks ---


@app.task(queue="reports")
async def generate_hourly_report() -> None:
    print("[TASK] Generating hourly report...")


@app.task(queue="emails")
async def send_daily_digest(include_analytics: bool = False) -> None:
    print(f"[TASK] Sending daily digest (analytics={include_analytics})...")


@app.task
async def heartbeat_check() -> None:
    print("[TASK] Heartbeat check OK.")


# --- Main ---


async def main() -> None:
    print("=== Fast-Potato Scheduled Tasks Demo ===\n")

    # Start the scheduler anchored at a base time
    base_time = datetime(2026, 9, 7, 8, 59, 0, tzinfo=UTC)  # Monday 8:59 AM
    scheduler = Scheduler(app=app, start_time=base_time)
    worker = Worker(app=app, queues=["default", "reports", "emails"])

    print(f"Scheduler initialized at: {base_time.isoformat()}")

    # 1. Advance time to 9:00 AM (Monday)
    # At 9:00 AM, both the heartbeat (* * * * *) and daily digest (9:00 AM weekdays) are due
    t1 = base_time + timedelta(minutes=1)
    print(f"\n--- Advancing time to {t1.strftime('%H:%M:%S')} ---")
    dispatched = await scheduler.tick(now=t1)
    print(f"Dispatched {len(dispatched)} task(s): {[m.task_name for m in dispatched]}")

    print("\n--- Worker Processing Dispatched Tasks ---")
    worker_task = asyncio.create_task(worker.run())
    await asyncio.sleep(0.05)
    worker.stop()
    await worker_task
    print("Worker finished executing dispatched tasks.")

    # 2. Advance time to 10:00 AM
    # At 10:00 AM, hourly report (0 * * * *) and heartbeat (* * * * *) are due
    t2 = base_time + timedelta(hours=1, minutes=1)
    print(f"\n--- Advancing time to {t2.strftime('%H:%M:%S')} ---")
    dispatched = await scheduler.tick(now=t2)
    print(f"Dispatched {len(dispatched)} task(s): {[m.task_name for m in dispatched]}")

    print("\n--- Worker Processing Dispatched Tasks ---")
    worker_task = asyncio.create_task(worker.run())
    await asyncio.sleep(0.05)
    worker.stop()
    await worker_task
    print("Worker finished executing dispatched tasks.")


if __name__ == "__main__":
    asyncio.run(main())
