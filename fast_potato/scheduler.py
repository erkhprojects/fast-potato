from __future__ import annotations

import asyncio
import logging
import signal
from datetime import UTC, datetime

from croniter import croniter

from fast_potato import app, message, schedule, worker

logger = logging.getLogger("fast_potato.scheduler")


class _ScheduleEntry:
    def __init__(self, sched: schedule.Schedule, start_time: datetime) -> None:
        self.schedule = sched
        self.cron = croniter(sched.cron, start_time)
        self.next_run = self.cron.get_next(datetime)


class Scheduler:
    """
    Cron scheduler that evaluates app.schedules and dispatches due tasks to the broker.
    """

    def __init__(self, app: app.FastPotato, start_time: datetime | None = None) -> None:
        self.app = app
        self._running = False
        self._stop_event = asyncio.Event()
        start = start_time or datetime.now(tz=UTC)
        self._entries = [_ScheduleEntry(s, start) for s in app.schedules]

    async def tick(self, now: datetime | None = None) -> list[message.TaskMessage]:
        """
        Evaluate all schedules against current time and dispatch any due tasks.
        Returns the list of dispatched TaskMessages.
        """
        current_time = now or datetime.now(tz=UTC)
        dispatched: list[message.TaskMessage] = []

        for entry in self._entries:
            if current_time >= entry.next_run:
                try:
                    task = self.app.get_task(entry.schedule.task)
                    msg = await task.send(
                        *entry.schedule.args,
                        queue=entry.schedule.queue,
                        **entry.schedule.kwargs,
                    )
                    dispatched.append(msg)
                    logger.info(
                        "Scheduler dispatched task '%s' (message ID: %s)",
                        entry.schedule.task,
                        msg.id,
                    )
                except Exception as exc:
                    logger.exception(
                        "Scheduler error dispatching task '%s': %s",
                        entry.schedule.task,
                        exc,
                    )
                finally:
                    entry.next_run = entry.cron.get_next(datetime)

        return dispatched

    async def run(self) -> None:
        """
        Run the scheduler loop until stopped.
        """
        self._running = True
        self._stop_event.clear()
        logger.info("Scheduler started with %d scheduled task(s).", len(self._entries))

        async with self.app.broker:
            while self._running:
                now = datetime.now(tz=UTC)
                await self.tick(now)

                if self._entries:
                    next_run_time = min(e.next_run for e in self._entries)
                    sleep_seconds = max(
                        0.1,
                        (next_run_time - datetime.now(tz=UTC)).total_seconds(),
                    )
                else:
                    sleep_seconds = 1.0

                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=min(sleep_seconds, 1.0),
                    )
                    break
                except TimeoutError:
                    pass

        logger.info("Scheduler stopped cleanly.")

    def stop(self) -> None:
        """Signal the scheduler to stop running."""
        self._running = False
        self._stop_event.set()


def run_scheduler(app_str: str, log_level: str = "INFO") -> None:
    """
    Entrypoint to run the scheduler in a dedicated process.
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(process)d] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    app = worker.import_app(app_str)
    app.autodiscover()

    sched = Scheduler(app=app)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _sig_handler() -> None:
        sched.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _sig_handler)
        except NotImplementedError, RuntimeError:
            signal.signal(sig, lambda *_: _sig_handler())

    try:
        loop.run_until_complete(sched.run())
    finally:
        loop.close()
