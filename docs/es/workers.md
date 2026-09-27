# Workers y CLI

```bash
fast-potato -A shop:app
```

| Opción | Significado | Valor por defecto |
|---|---|---|
| `-A`, `--app` | Ruta de importación de la app, `module:attribute` | obligatorio |
| `-q`, `--queues` | Colas a consumir, separadas por comas | `default` |
| `-c`, `--concurrency` | Tareas ejecutándose a la vez por proceso | `10` |
| `-w`, `--processes` | Procesos worker | `1` |
| `--log-level` | `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |

```bash
# two processes, 20 concurrent tasks each, two queues
fast-potato -A shop:app -w 2 -c 20 -q orders,emails
```

Si la app tiene programaciones, la CLI también inicia un proceso programador
([Programación de tareas](scheduling.md)).

`-A shop` también funciona: busca `app` en `shop`, o la única instancia de `FastPotato`
que haya allí.

## Encontrar las tareas

El worker debe importar los módulos que definen tus tareas. Enuméralos en la
app y la CLI los importa al arrancar:

```python
app = FastPotato("shop", broker=broker, task_modules=["shop.orders", "shop.emails"])
```

## Apagado

`SIGINT`/`SIGTERM` hacen que cada worker deje de consumir y espere a que sus tareas en ejecución
terminen. La CLI le da a cada proceso 3 segundos; después de eso, el
proceso se termina forzosamente.

## Ejecutar un worker desde el código

```python
from fast_potato import Worker

worker = Worker(app, queues=["orders"], concurrency=5)
await worker.run()   # until worker.stop() is called
```
