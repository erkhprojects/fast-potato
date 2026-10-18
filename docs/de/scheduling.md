# Zeitplanung

```python
from fast_potato import FastPotato, Schedule, crontab


class ReportInput(BaseModel):
    period: str


app = FastPotato(
    "shop",
    broker=broker,
    schedules=[
        Schedule(task="shop.cleanup", cron="0 3 * * *"),
        Schedule(
            task="shop.send_report",
            cron=crontab(minute="0", hour="8"),
            payload=ReportInput(period="daily"),
        ),
        Schedule(
            task="shop.send_report",
            cron=crontab(minute="0", hour="8", day_of_week="1"),
            payload=ReportInput(period="weekly"),
            queue="reports",
        ),
    ],
)


@app.task
async def cleanup() -> None: ...


@app.task
async def send_report(report: ReportInput) -> None: ...
```

- `task` ist `"<app name>.<function name>"`.
- `cron` ist ein standardmäßiger Ausdruck mit 5 Feldern. `crontab()` baut einen aus benannten Teilen.
- `payload` ist erforderlich, wenn die Task ein Eingabemodell nimmt, und muss
  exakt dieses Modell sein. Lass es bei Tasks ohne Eingabe weg.
- `queue` überschreibt die Standard-Queue der Task.

`fast-potato -A shop:app` startet den Scheduler automatisch, wenn die App
Zeitpläne hat.

!!! warning
    Zeitpläne referenzieren Tasks über ihren Namen, daher wird ein falsches `payload` nicht von
    mypy erkannt. Es wird geloggt, und dieser Lauf wird übersprungen, wenn der Zeitplan auslöst.
