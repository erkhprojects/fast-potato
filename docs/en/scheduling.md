# Scheduling

```python
from fast_potato import FastPotato, Schedule, crontab


class ReportInput(BaseModel):
    period: str


app = FastPotato(
    "shop",
    broker=broker,
    schedules=[
        Schedule(task="shop.cleanup", cron="0 3 * * *"),
        Schedule(task="shop.send_report", cron=crontab(minute="0", hour="8"),
                 payload=ReportInput(period="daily")),
        Schedule(task="shop.send_report", cron=crontab(minute="0", hour="8", day_of_week="1"),
                 payload=ReportInput(period="weekly"), queue="reports"),
    ],
)


@app.task
async def cleanup() -> None: ...


@app.task
async def send_report(report: ReportInput) -> None: ...
```

- `task` is `"<app name>.<function name>"`.
- `cron` is a standard 5-field expression. `crontab()` builds one from named parts.
- `payload` is required when the task takes an input model, and must be
  exactly that model. Leave it out for tasks without input.
- `queue` overrides the task's default queue.

`fast-potato -A shop:app` starts the scheduler automatically when the app has
schedules.

!!! warning
    Schedules refer to tasks by name, so a wrong `payload` isn't caught by
    mypy. It's logged, and that run is skipped, when the schedule fires.
