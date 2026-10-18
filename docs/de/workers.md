# Worker & CLI

```bash
fast-potato -A shop:app
```

| Flag | Bedeutung | Standard |
|---|---|---|
| `-A`, `--app` | Importpfad der App, `module:attribute` | erforderlich |
| `-q`, `--queues` | Kommagetrennte Queues, die konsumiert werden | `default` |
| `-c`, `--concurrency` | Gleichzeitig laufende Tasks pro Prozess | `10` |
| `-w`, `--processes` | Worker-Prozesse | `1` |
| `--log-level` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |

```bash
# two processes, 20 concurrent tasks each, two queues
fast-potato -A shop:app -w 2 -c 20 -q orders,emails
```

Wenn die App Zeitpläne hat, startet die CLI zusätzlich einen Scheduler-Prozess
([Zeitplanung](scheduling.md)).

`-A shop` funktioniert auch: Es findet `app` in `shop` oder die einzige `FastPotato`-Instanz
dort.

## Tasks finden

Der Worker muss die Module importieren, die deine Tasks definieren. Liste sie in der
App auf, und die CLI importiert sie beim Start:

```python
app = FastPotato("shop", broker=broker, task_modules=["shop.orders", "shop.emails"])
```

## Herunterfahren

`SIGINT`/`SIGTERM` bringen jeden Worker dazu, keine Nachrichten mehr zu konsumieren und auf das Ende seiner laufenden
Tasks zu warten. Die CLI gibt jedem Prozess 3 Sekunden; danach wird der
Prozess zwangsweise beendet.

## Einen Worker im Code ausführen

```python
from fast_potato import Worker

worker = Worker(app, queues=["orders"], concurrency=5)
await worker.run()  # until worker.stop() is called
```
