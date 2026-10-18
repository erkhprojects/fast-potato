# Workers & CLI

```bash
fast-potato -A shop:app
```

| Flag | Meaning | Default |
|---|---|---|
| `-A`, `--app` | App import path, `module:attribute` | required |
| `-q`, `--queues` | Comma-separated queues to consume | `default` |
| `-c`, `--concurrency` | Tasks running at once per process | `10` |
| `-w`, `--processes` | Worker processes | `1` |
| `--log-level` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |

```bash
# two processes, 20 concurrent tasks each, two queues
fast-potato -A shop:app -w 2 -c 20 -q orders,emails
```

If the app has schedules, the CLI also starts one scheduler process
([Scheduling](scheduling.md)).

`-A shop` also works: it finds `app` in `shop`, or the only `FastPotato`
instance there.

## Finding tasks

The worker must import the modules that define your tasks. List them on the
app and the CLI imports them at startup:

```python
app = FastPotato("shop", broker=broker, task_modules=["shop.orders", "shop.emails"])
```

## Shutdown

`SIGINT`/`SIGTERM` make each worker stop consuming and wait for its running
tasks to finish. The CLI gives each process 3 seconds; after that, the
process is killed.

## Running a worker in code

```python
from fast_potato import Worker

worker = Worker(app, queues=["orders"], concurrency=5)
await worker.run()  # until worker.stop() is called
```
