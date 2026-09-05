from __future__ import annotations

import pytest
from pydantic import ValidationError

from fast_potato import FastPotato, Schedule
from fast_potato.brokers import MemoryBroker


def make_app(**kwargs) -> FastPotato:
    return FastPotato("my_app", broker=MemoryBroker(), **kwargs)


class TestScheduleValidation:
    def test_valid_cron_accepted(self):
        s = Schedule(task="my_app.task", cron="0 * * * *")
        assert s.cron == "0 * * * *"

    def test_invalid_cron_raises(self):
        with pytest.raises(ValidationError, match="Invalid cron expression"):
            Schedule(task="my_app.task", cron="not-a-cron")

    def test_too_few_fields_raises(self):
        with pytest.raises(ValidationError, match="Invalid cron expression"):
            Schedule(task="my_app.task", cron="* * * *")

    def test_out_of_range_values_raise(self):
        # minute 99 is out of range
        with pytest.raises(ValidationError, match="Invalid cron expression"):
            Schedule(task="my_app.task", cron="99 * * * *")

    def test_wildcard_cron_accepted(self):
        s = Schedule(task="my_app.task", cron="* * * * *")
        assert s.cron == "* * * * *"

    def test_defaults(self):
        s = Schedule(task="my_app.task", cron="0 9 * * 1")
        assert s.queue is None
        assert s.args == []
        assert s.kwargs == {}

    def test_custom_queue(self):
        s = Schedule(task="my_app.task", cron="0 * * * *", queue="reports")
        assert s.queue == "reports"

    def test_args_and_kwargs_stored(self):
        s = Schedule(
            task="my_app.task",
            cron="0 * * * *",
            args=[1, 2],
            kwargs={"full": True},
        )
        assert s.args == [1, 2]
        assert s.kwargs == {"full": True}


class TestFastPotatoSchedules:
    def test_app_stores_schedules(self):
        schedules = [
            Schedule(task="my_app.process_reports", cron="0 * * * *"),
            Schedule(task="my_app.send_digest", cron="0 9 * * 1"),
        ]
        app = make_app(schedules=schedules)
        assert len(app.schedules) == 2

    def test_app_defaults_to_empty_schedules(self):
        app = make_app()
        assert app.schedules == []

    def test_schedule_task_names_stored(self):
        schedules = [Schedule(task="my_app.hourly_job", cron="0 * * * *")]
        app = make_app(schedules=schedules)
        assert app.schedules[0].task == "my_app.hourly_job"

    def test_multiple_schedules_for_different_tasks(self):
        schedules = [
            Schedule(task="my_app.job_a", cron="0 * * * *"),
            Schedule(task="my_app.job_b", cron="0 9 * * 1"),
            Schedule(task="my_app.job_c", cron="*/15 * * * *"),
        ]
        app = make_app(schedules=schedules)
        tasks = [s.task for s in app.schedules]
        assert tasks == ["my_app.job_a", "my_app.job_b", "my_app.job_c"]

    def test_invalid_schedule_raises_before_app_starts(self):
        with pytest.raises(ValidationError, match="Invalid cron expression"):
            make_app(schedules=[Schedule(task="my_app.job", cron="bad")])

    def test_schedule_with_queue_override(self):
        schedules = [Schedule(task="my_app.report", cron="0 6 * * *", queue="reports")]
        app = make_app(schedules=schedules)
        assert app.schedules[0].queue == "reports"

    def test_schedule_with_static_kwargs(self):
        schedules = [
            Schedule(task="my_app.digest", cron="0 9 * * 1", kwargs={"full": True})
        ]
        app = make_app(schedules=schedules)
        assert app.schedules[0].kwargs == {"full": True}
