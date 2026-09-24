from __future__ import annotations

from croniter import croniter
from pydantic import BaseModel, InstanceOf, SerializeAsAny, field_validator


class Schedule(BaseModel):
    """
    Defines when a registered task should be triggered automatically.

    Pass a list of Schedule objects to FastPotato at initialization:

        app = FastPotato(
            "my_app",
            broker=RedisBroker(...),
            schedules=[
                Schedule(task="my_app.process_reports", cron="0 * * * *"),
                Schedule(task="my_app.send_digest",     cron="0 9 * * 1",
                         queue="emails", payload=DigestInput(full=True)),
            ],
        )

    Fields:
        task:   Fully-qualified task name as registered in the app registry,
                i.e. "<app_name>.<function_qualname>".
        cron:   Standard 5-field cron expression (minute hour day month weekday).
        queue:  Queue to push the task onto. Defaults to the task's own queue
                when None — resolved at beat time.
        payload: Input model instance sent on every trigger, for tasks that
                take an input model. Leave None for tasks without input.
    """

    task: str
    cron: str
    queue: str | None = None
    # InstanceOf: the payload's concrete model can't be inferred from raw data, so
    # only real instances are accepted. SerializeAsAny: dump the concrete model's
    # fields rather than the (empty) BaseModel schema.
    payload: SerializeAsAny[InstanceOf[BaseModel]] | None = None

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        if not croniter.is_valid(v):
            raise ValueError(
                f"Invalid cron expression: {v!r}. Expected 5 fields, e.g. '0 * * * *'."
            )
        return v


def crontab(
    minute: str = "*",
    hour: str = "*",
    day: str = "*",
    month: str = "*",
    day_of_week: str = "*",
) -> str:
    """Helper to build a 5-field cron expression from named parts."""
    expr = f"{minute} {hour} {day} {month} {day_of_week}"
    if not croniter.is_valid(expr):
        raise ValueError(f"Invalid cron expression: {expr!r}")
    return expr
