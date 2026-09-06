from __future__ import annotations

import asyncio
import importlib
import logging
import os
import signal
import sys
import types
import typing
from typing import Any, get_args, get_origin

from pydantic import BaseModel

from fast_potato import dependency, message
from fast_potato.app import FastPotato

logger = logging.getLogger("fast_potato.worker")


def deserialize_value(
        val: Any,
        annotation: Any = None,
        globals_dict: dict[str, Any] | None = None,
) -> Any:
    """
    Recursively deserialize arguments back into their target types.

    Reconstructs Pydantic models serialized as:
    ``{"__pydantic__": "ModelName", "data": {...}}``
    or plain dicts when the parameter annotation expects a BaseModel subclass.
    """
    # 1. Handle Union types (e.g. User | None or Optional[User])
    if get_origin(annotation) in (typing.Union, types.UnionType):
        for u_arg in get_args(annotation):
            if isinstance(u_arg, type) and issubclass(u_arg, BaseModel):
                try:
                    return deserialize_value(val, u_arg, globals_dict)
                except Exception:
                    pass

    # 2. Reconstruct from explicit Pydantic serialization envelope
    if isinstance(val, dict) and "__pydantic__" in val and "data" in val:
        cls_name = val["__pydantic__"]
        data = val["data"]

        # Check annotation first
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return annotation.model_validate(data)

        # Fallback to module globals of the task function
        if globals_dict and cls_name in globals_dict:
            target_cls = globals_dict[cls_name]
            if isinstance(target_cls, type) and issubclass(target_cls, BaseModel):
                return target_cls.model_validate(data)

        return data

    # 3. Model expected by annotation and raw dict provided
    if isinstance(annotation, type) and issubclass(annotation, BaseModel) and isinstance(val, dict):
        return annotation.model_validate(val)

    # 4. List annotations (e.g. list[User])
    if get_origin(annotation) is list and isinstance(val, list):
        args = get_args(annotation)
        item_type = args[0] if args else Any
        return [deserialize_value(item, item_type, globals_dict) for item in val]

    # 5. Nested untyped lists or dicts
    if isinstance(val, list):
        return [deserialize_value(item, Any, globals_dict) for item in val]
    if isinstance(val, dict):
        return {k: deserialize_value(v, Any, globals_dict) for k, v in val.items()}

    return val


class Worker:
    """
    Async task execution worker for FastPotato.

    Consumes TaskMessage objects from broker queues, deserializes Pydantic models,
    resolves dependency injection via DependencyResolver, and executes tasks
    under bounded concurrency enforced by an asyncio.Semaphore.
    """

    def __init__(
            self,
            app: FastPotato,
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

    async def process_message(self, msg: message.TaskMessage) -> Any:
        """
        Execute a single task message and return its result.

        Raises exceptions directly if task lookup, deserialization, or execution fails.
        """
        task = self.app.get_task(msg.task_name)
        sig = task._sig
        hints = dependency.resolved_hints(task._fn)
        globals_dict = getattr(task._fn, "__globals__", {})

        # Bind raw args and kwargs to signature
        bound = sig.bind_partial(*msg.args, **msg.kwargs)

        # Deserialize arguments matching parameters
        for name, val in list(bound.arguments.items()):
            if name not in task.dependency_params:
                annotation = hints.get(name)
                bound.arguments[name] = deserialize_value(val, annotation, globals_dict)

        # Resolve dependencies (Depends / Potato)
        async with dependency.DependencyResolver(potato=self.app.potato) as resolver:
            injected = await resolver.resolve_params(task._fn)
            for dep_name, dep_val in injected.items():
                bound.arguments[dep_name] = dep_val

            bound.apply_defaults()
            return await task._fn(*bound.args, **bound.kwargs)

    async def _safe_execute(self, msg: message.TaskMessage) -> Any:
        """
        Execute a message with logging and exception suppression so the worker loop survives.
        """
        logger.info("Task %s[%s] received on queue '%s'", msg.task_name, msg.id, msg.queue)
        try:
            result = await self.process_message(msg)
            logger.info("Task %s[%s] completed successfully", msg.task_name, msg.id)
            return result
        except Exception as exc:
            logger.exception("Task %s[%s] failed: %s", msg.task_name, msg.id, exc)
            return None

    async def process_one(self, msg: message.TaskMessage) -> Any:
        """
        Convenience method to execute a single task message directly.
        Returns the result or propagates any exception.
        """
        return await self.process_message(msg)

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

        async with self.app.broker:
            async for msg in self.app.broker.consume(self.queues):
                if not self._running:
                    break

                # Backpressure: wait for an available concurrency slot
                await self._semaphore.acquire()

                async def _task_wrapper(m: message.TaskMessage) -> None:
                    try:
                        await self._safe_execute(m)
                    finally:
                        self._semaphore.release()

                task = asyncio.create_task(_task_wrapper(msg))
                self._active_tasks.add(task)
                task.add_done_callback(self._active_tasks.discard)

                if not self._running:
                    break

        await self._drain()

    async def _drain(self) -> None:
        """Wait for active in-flight tasks to finish during graceful shutdown."""
        if self._active_tasks:
            logger.info("Worker waiting for %d active tasks to complete...", len(self._active_tasks))
            await asyncio.gather(*list(self._active_tasks), return_exceptions=True)
        logger.info("Worker stopped cleanly.")

    def stop(self) -> None:
        """Signal the worker to stop consuming and shut down gracefully."""
        self._running = False
        self._stop_event.set()

    async def run_until_empty(self) -> int:
        """
        Consume and process all currently available messages in the configured queues.
        Returns the count of processed messages.
        """
        self._running = True
        count = 0
        async with self.app.broker:
            async for msg in self.app.broker.consume(self.queues):
                await self._safe_execute(msg)
                count += 1
        self._running = False
        return count


def import_app(app_str: str) -> FastPotato:
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
            raise ImportError(f"Could not import module '{module_name}': {exc}") from exc

        try:
            app = getattr(module, attr_name)
        except AttributeError as exc:
            raise AttributeError(
                f"Module '{module_name}' has no attribute '{attr_name}'."
            ) from exc
    else:
        module_name = app_str
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            raise ImportError(f"Could not import module '{module_name}': {exc}") from exc

        if hasattr(module, "app") and isinstance(module.app, FastPotato):
            app = module.app
        else:
            candidates = [v for v in module.__dict__.values() if isinstance(v, FastPotato)]
            if len(candidates) == 1:
                app = candidates[0]
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

    if not isinstance(app, FastPotato):
        raise TypeError(
            f"Target '{app_str}' resolved to {type(app).__name__}, expected a FastPotato instance."
        )

    return app


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
        except (NotImplementedError, RuntimeError):
            signal.signal(sig, lambda *_: _sig_handler())

    try:
        loop.run_until_complete(worker.run())
    finally:
        loop.close()
