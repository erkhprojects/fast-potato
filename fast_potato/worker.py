from __future__ import annotations

import asyncio
import importlib
import logging
import os
import signal
import sys
from contextlib import aclosing
from typing import Any

from fast_potato import app as app_module
from fast_potato import dependency, message

logger = logging.getLogger("fast_potato.worker")


class Worker:
    """
    Async task execution worker for FastPotato.

    Consumes TaskMessage objects from broker queues, deserializes Pydantic models,
    resolves dependency injection via DependencyResolver, and executes tasks
    under bounded concurrency enforced by an asyncio.Semaphore.
    """

    def __init__(
        self,
        app: app_module.FastPotato,
        queues: list[str] | None = None,
        concurrency: int = 10,
    ) -> None:
        self.app = app
        self.queues = list(queues) if queues is not None else ["default"]
        self.concurrency = max(1, concurrency)
        self._semaphore = asyncio.Semaphore(self.concurrency)
        self._running = False
        self._stop_event = asyncio.Event()
        self._active_tasks: set[asyncio.Task] = set()

    @property
    def running(self) -> bool:
        """Whether the worker loop is currently running."""
        return self._running

    @property
    def active_tasks(self) -> set[asyncio.Task]:
        """Set of currently running background asyncio.Tasks."""
        return self._active_tasks

    async def execute(self, msg: message.TaskMessage) -> Any:
        """
        Execute a single task message and return its result.

        Raises exceptions directly if task lookup, deserialization, or execution fails.
        """
        task = self.app.get_task(msg.task_name)
        sig = task.sig
        hints = dependency.resolved_hints(task.fn)
        globals_dict = getattr(task.fn, "__globals__", {})

        # Bind raw args and kwargs to signature
        bound = sig.bind_partial(*msg.args, **msg.kwargs)

        # Deserialize arguments matching parameters
        for name, val in list(bound.arguments.items()):
            if name not in task.dependency_params:
                annotation = hints.get(name)
                bound.arguments[name] = message.deserialize_value(
                    val, annotation, globals_dict
                )

        # Resolve dependencies (Depends / Potato)
        async with dependency.DependencyResolver(potato=self.app.potato) as resolver:
            injected = await resolver.resolve_params(task.fn)
            for dep_name, dep_val in injected.items():
                bound.arguments[dep_name] = dep_val

            bound.apply_defaults()
            return await task.fn(*bound.args, **bound.kwargs)

    async def _safe_execute(self, msg: message.TaskMessage) -> Any:
        """
        Execute a message with logging and exception suppression so the worker loop survives.
        """
        logger.info(
            "Task %s[%s] received on queue '%s'", msg.task_name, msg.id, msg.queue
        )
        try:
            result = await self.execute(msg)
            logger.info("Task %s[%s] completed successfully", msg.task_name, msg.id)
            return result
        except Exception as exc:
            logger.exception("Task %s[%s] failed: %s", msg.task_name, msg.id, exc)
            return None

    def _on_task_done(self, task: asyncio.Task[Any]) -> None:
        """Clean up finished task tracking and release the concurrency semaphore."""
        self._active_tasks.discard(task)
        self._semaphore.release()

    async def run(self) -> None:
        """
        Start consuming messages from the broker indefinitely until stopped.
        """
        self._running = True
        self._stop_event.clear()
        logger.info(
            "Worker started for app '%s' on queues %s (concurrency=%d)",
            self.app.name,
            self.queues,
            self.concurrency,
        )

        try:
            async with (
                self.app.broker,
                aclosing(self.app.broker.consume(self.queues)) as consumer,
            ):
                while self._running:
                    next_msg_task = asyncio.create_task(anext(consumer))
                    stop_wait_task = asyncio.create_task(self._stop_event.wait())

                    _, pending = await asyncio.wait(
                        [next_msg_task, stop_wait_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    for p in pending:
                        p.cancel()
                    await asyncio.gather(*pending, return_exceptions=True)

                    if self._stop_event.is_set() or not self._running:
                        break

                    msg = next_msg_task.result()

                    # Backpressure: wait for an available concurrency slot
                    await self._semaphore.acquire()

                    task = asyncio.create_task(self._safe_execute(msg))
                    self._active_tasks.add(task)
                    task.add_done_callback(self._on_task_done)
        except asyncio.CancelledError:
            self._running = False
        finally:
            await self._drain()

    async def _drain(self) -> None:
        """Wait for active in-flight tasks to finish during graceful shutdown."""
        if self._active_tasks:
            logger.info(
                "Worker waiting for %d active tasks to complete...",
                len(self._active_tasks),
            )
            await asyncio.gather(*list(self._active_tasks), return_exceptions=True)
        logger.info("Worker stopped cleanly.")

    def stop(self) -> None:
        """Signal the worker to stop consuming and shut down gracefully."""
        self._running = False
        self._stop_event.set()


def import_app(app_str: str) -> app_module.FastPotato:
    """
    Import and return a FastPotato application instance.

    Supported formats:
        - "module_name:app_attr" (e.g. "examples.basic_usage:app")
        - "module_name" (looks for an attribute named 'app' or a single FastPotato instance)
    """
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)

    if ":" in app_str:
        module_name, attr_name = app_str.split(":", 1)
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            raise ImportError(
                f"Could not import module '{module_name}': {exc}"
            ) from exc

        try:
            app_obj = getattr(module, attr_name)
        except AttributeError as exc:
            raise AttributeError(
                f"Module '{module_name}' has no attribute '{attr_name}'."
            ) from exc
    else:
        module_name = app_str
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            raise ImportError(
                f"Could not import module '{module_name}': {exc}"
            ) from exc

        if hasattr(module, "app") and isinstance(module.app, app_module.FastPotato):
            app_obj = module.app
        else:
            candidates = [
                v for v in module.__dict__.values() if isinstance(v, app_module.FastPotato)
            ]
            if len(candidates) == 1:
                app_obj = candidates[0]
            elif len(candidates) > 1:
                raise ValueError(
                    f"Multiple FastPotato instances found in '{module_name}'. "
                    "Specify which one to use with 'module:app_name'."
                )
            else:
                raise AttributeError(
                    f"No FastPotato instance found in module '{module_name}'. "
                    "Specify the attribute with 'module:app_name'."
                )

    if not isinstance(app_obj, app_module.FastPotato):
        raise TypeError(
            f"Target '{app_str}' resolved to {type(app_obj).__name__}, expected a FastPotato instance."
        )

    return app_obj


def run_worker(
    app_str: str,
    queues: list[str] | None = None,
    concurrency: int = 10,
    log_level: str = "INFO",
) -> None:
    """
    Unified worker entrypoint used by both single-process and multi-process modes.

    Configures logging, imports the application, discovers tasks, registers
    OS signal handlers, and runs the Worker event loop to completion.
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(process)d] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    app = import_app(app_str)
    app.autodiscover()

    worker = Worker(app=app, queues=queues, concurrency=concurrency)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _sig_handler() -> None:
        worker.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _sig_handler)
        except NotImplementedError, RuntimeError:
            signal.signal(sig, lambda *_: _sig_handler())

    try:
        loop.run_until_complete(worker.run())
    finally:
        loop.close()
