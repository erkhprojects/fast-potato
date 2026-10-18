# Programación de tareas

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

- `task` es `"<app name>.<function name>"`.
- `cron` es una expresión estándar de 5 campos. `crontab()` construye una a partir de partes con nombre.
- `payload` es obligatorio cuando la tarea recibe un modelo de entrada, y debe ser
  exactamente ese modelo. Omítelo para las tareas sin entrada.
- `queue` sobrescribe la cola por defecto de la tarea.

`fast-potato -A shop:app` inicia el programador automáticamente cuando la app tiene
programaciones.

!!! warning
    Las programaciones hacen referencia a las tareas por nombre, así que mypy no detecta un `payload` incorrecto.
    Se registra en el log, y esa ejecución se omite, cuando se dispara la programación.
