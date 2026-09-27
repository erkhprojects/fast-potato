# Workers et CLI

```bash
fast-potato -A shop:app
```

| Option | Signification | Par défaut |
|---|---|---|
| `-A`, `--app` | Chemin d'import de l'app, `module:attribute` | obligatoire |
| `-q`, `--queues` | Files d'attente à consommer, séparées par des virgules | `default` |
| `-c`, `--concurrency` | Tâches exécutées simultanément par processus | `10` |
| `-w`, `--processes` | Processus worker | `1` |
| `--log-level` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |

```bash
# two processes, 20 concurrent tasks each, two queues
fast-potato -A shop:app -w 2 -c 20 -q orders,emails
```

Si l'app a des planifications, la CLI démarre aussi un processus de planification
([Planification](scheduling.md)).

`-A shop` fonctionne aussi : il trouve `app` dans `shop`, ou l'unique instance de `FastPotato`
qui s'y trouve.

## Trouver les tâches

Le worker doit importer les modules qui définissent vos tâches. Listez-les sur
l'app et la CLI les importe au démarrage :

```python
app = FastPotato("shop", broker=broker, task_modules=["shop.orders", "shop.emails"])
```

## Arrêt

`SIGINT`/`SIGTERM` font que chaque worker cesse de consommer et attend la fin de ses tâches
en cours. La CLI accorde 3 secondes à chaque processus ; passé ce délai, le
processus est tué.

## Lancer un worker dans le code

```python
from fast_potato import Worker

worker = Worker(app, queues=["orders"], concurrency=5)
await worker.run()   # until worker.stop() is called
```
