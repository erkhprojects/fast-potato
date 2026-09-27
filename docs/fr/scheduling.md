# Planification

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

- `task` vaut `"<app name>.<function name>"`.
- `cron` est une expression standard à 5 champs. `crontab()` en construit une à partir de parties nommées.
- `payload` est obligatoire lorsque la tâche prend un modèle d'entrée, et doit être
  exactement ce modèle. Omettez-le pour les tâches sans entrée.
- `queue` remplace la file d'attente par défaut de la tâche.

`fast-potato -A shop:app` démarre automatiquement le planificateur lorsque l'app a des
planifications.

!!! warning
    Les planifications font référence aux tâches par leur nom, donc un `payload` incorrect n'est pas détecté par
    mypy. Il est journalisé, et cette exécution est ignorée, au déclenchement de la planification.
