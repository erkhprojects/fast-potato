from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fast_potato import FastPotato, Schedule, Scheduler
from fast_potato.brokers import MemoryBroker


def make_app_with_schedules(
    schedules: list[Schedule] | None = None,
) -> tuple[FastPotato, MemoryBroker]:
    broker = MemoryBroker()
    app = FastPotato(
        "test_app",
        broker=broker,
        schedules=schedules or [],
    )
    return app, broker


class TestSchedulerTick:
    async def test_scheduler_dispatches_due_task(self):
        broker = MemoryBroker()
        app = FastPotato("test_app", broker=broker)

        @app.task
        async def hourly_job() -> str:
            return "done"

        sched = Schedule(task=hourly_job.name, cron="* * * * *")
        app.schedules = [sched]

        # Initialize scheduler starting at 10:00:00 UTC
        start_time = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
        scheduler = Scheduler(app=app, start_time=start_time)

        # At 10:00:30 UTC: not due yet (next run is 10:01:00)
        t1 = datetime(2026, 1, 1, 10, 0, 30, tzinfo=UTC)
        msgs = await scheduler.tick(now=t1)
        assert len(msgs) == 0
        assert len(broker.published) == 0

        # At 10:01:00 UTC: now it is due!
        t2 = datetime(2026, 1, 1, 10, 1, 0, tzinfo=UTC)
        msgs = await scheduler.tick(now=t2)
        assert len(msgs) == 1
        assert msgs[0].task_name == hourly_job.name
        assert len(broker.published) == 1

        # Calling tick again at 10:01:10 UTC should not re-dispatch (next run is 10:02:00)
        t3 = datetime(2026, 1, 1, 10, 1, 10, tzinfo=UTC)
        msgs2 = await scheduler.tick(now=t3)
        assert len(msgs2) == 0
        assert len(broker.published) == 1

    async def test_scheduler_passes_args_kwargs_and_queue(self):
        broker = MemoryBroker()
        app = FastPotato("test_app", broker=broker)

        @app.task
        async def send_report(report_id: int, format: str = "html") -> None:
            pass

        sched = Schedule(
            task=send_report.name,
            cron="* * * * *",
            queue="reports",
            args=[123],
            kwargs={"format": "pdf"},
        )
        app.schedules = [sched]

        start_time = datetime(2026, 1, 1, 10, 0, 0, tzinfo=UTC)
        scheduler = Scheduler(app=app, start_time=start_time)

        due_time = datetime(2026, 1, 1, 10, 1, 0, tzinfo=UTC)
        msgs = await scheduler.tick(now=due_time)

        assert len(msgs) == 1
        assert msgs[0].queue == "reports"
        assert msgs[0].args == [123]
        assert msgs[0].kwargs == {"format": "pdf"}

    async def test_scheduler_run_and_stop(self):
        app, broker = make_app_with_schedules([])
        scheduler = Scheduler(app=app)

        run_task = asyncio.create_task(scheduler.run())
        await asyncio.sleep(0.05)
        scheduler.stop()
        await run_task
        assert not scheduler._running
