"""
Test helpers for applications built on fast-potato.

Wrap your app in TestApp for the duration of a test. It swaps in an in-memory
broker, lets you override dependencies and the potato, and restores everything
on exit. Tasks always run through the same code path as the real Worker, with
a JSON round-trip of the message, so serialization bugs surface in tests.

Two ways to run tasks:

    # Drain (default): send() queues; drain() runs the queue in FIFO order,
    # including tasks enqueued by other tasks.
    with TestApp(app) as t:
        await checkout(Order(order_id=1))
        t.assert_sent(send_receipt, Receipt(order_id=1))
        await t.drain()

    # Eager: every send() runs the task immediately, before send() returns.
    with TestApp(app, eager=True) as t:
        await checkout(Order(order_id=1))

In both modes a failing task raises into the test by default. Pass
raise_errors=False to collect failures in t.errors instead.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, overload

from pydantic import BaseModel

from fast_potato import app as app_module
from fast_potato import message, worker
from fast_potato import task as task_module
from fast_potato.brokers import base, memory

logger = logging.getLogger("fast_potato.testing")


def _round_trip(msg: message.TaskMessage) -> message.TaskMessage:
    """Serialize and parse the message as a real broker would."""
    return message.TaskMessage.model_validate_json(msg.model_dump_json())


@dataclass
class TaskRun:
    """Record of one task execution performed by TestApp."""

    msg: message.TaskMessage
    result: Any = None
    error: Exception | None = None


class EagerBroker(memory.MemoryBroker):
    """
    Broker that runs each task inside publish(), i.e. before send() returns.

    Messages are recorded in ``history`` but never queued. Delays and ETAs are
    ignored. Usually created for you by ``TestApp(app, eager=True)``.
    """

    def __init__(
        self,
        run: Callable[[message.TaskMessage], Awaitable[TaskRun]],
    ) -> None:
        super().__init__()
        self._run = run

    async def publish(self, msg: message.TaskMessage) -> None:
        self.history.append(msg)
        await self._run(msg)


class TestApp:
    """
    Context manager that puts a FastPotato app into test mode.

    On enter it replaces ``app.broker`` (MemoryBroker, or EagerBroker when
    ``eager=True``) and optionally ``app.potato``. On exit it restores the
    broker, potato and dependency overrides.
    """

    __test__ = False  # not a pytest test class

    def __init__(
        self,
        app: app_module.FastPotato,
        *,
        eager: bool = False,
        potato: app_module.Potato | None = None,
        raise_errors: bool = True,
    ) -> None:
        self.app = app
        self.eager = eager
        self.raise_errors = raise_errors
        self.runs: list[TaskRun] = []
        self.broker: memory.MemoryBroker = (
            EagerBroker(self._run) if eager else memory.MemoryBroker()
        )
        self._potato = potato
        self._saved_broker: base.AbstractBroker | None = None
        self._saved_potato: app_module.Potato | None = None
        self._saved_overrides: dict[Callable[..., Any], Callable[..., Any]] = {}

    def __enter__(self) -> TestApp:
        self._saved_broker = self.app.broker
        self._saved_potato = self.app.potato
        self._saved_overrides = dict(self.app.dependency_overrides)
        self.app.broker = self.broker
        if self._potato is not None:
            self.app.potato = self._potato
        return self

    def __exit__(self, *_: object) -> None:
        assert self._saved_broker is not None
        self.app.broker = self._saved_broker
        self.app.potato = self._saved_potato
        self.app.dependency_overrides = self._saved_overrides

    # ------------------------------------------------------------------ setup

    def override(
        self,
        dependency: Callable[..., Any],
        replacement: Callable[..., Any],
    ) -> None:
        """Resolve ``Depends(dependency)`` with ``replacement`` until exit."""
        self.app.dependency_overrides[dependency] = replacement

    # ------------------------------------------------------------- inspection

    @property
    def messages(self) -> list[message.TaskMessage]:
        """Every message sent while in test mode, in send order."""
        return list(self.broker.history)

    @property
    def pending(self) -> list[message.TaskMessage]:
        """Messages queued but not yet run (always empty in eager mode)."""
        return list(self.broker.published)

    @property
    def errors(self) -> list[TaskRun]:
        """Runs that raised (only populated when raise_errors=False)."""
        return [r for r in self.runs if r.error is not None]

    def sent[InputT: BaseModel | None](
        self,
        task: task_module.Task[InputT, Any],
    ) -> list[InputT]:
        """Decoded input of every message sent for ``task``, in send order."""
        return [
            worker.decode_input(task, _round_trip(m))
            for m in self.broker.history
            if m.task_name == task.name
        ]

    @overload
    def assert_sent(self, task: task_module.Task[None, Any]) -> None: ...

    @overload
    def assert_sent[M: BaseModel](
        self,
        task: task_module.Task[M, Any],
        data: M,
    ) -> None: ...

    def assert_sent(
        self,
        task: task_module.Task[Any, Any],
        data: BaseModel | None = None,
    ) -> None:
        """Assert ``task`` was sent at least once (with exactly this input, if any)."""
        calls = self.sent(task)
        if data not in calls:
            expected = "no input" if data is None else repr(data)
            raise AssertionError(
                f"{task.name} was not sent with {expected}. Sent: {calls}"
            )

    def assert_not_sent(self, task: task_module.Task[Any, Any]) -> None:
        """Assert ``task`` was never sent."""
        calls = self.sent(task)
        if calls:
            raise AssertionError(f"{task.name} was sent {len(calls)} time(s): {calls}")

    # ---------------------------------------------------------------- running

    async def drain(
        self,
        *,
        queues: list[str] | None = None,
        run_delayed: bool = True,
        max_tasks: int = 1000,
    ) -> list[TaskRun]:
        """
        Run queued messages in FIFO order until nothing runnable is left.

        Tasks sent by running tasks are picked up in the same call.

        Args:
            queues: Only run messages from these queues (default: all).
            run_delayed: Run messages whose ETA is in the future. When False
                they stay queued in ``pending``.
            max_tasks: Safety limit against tasks that keep re-enqueueing
                themselves; exceeding it raises RuntimeError.
        """
        runs: list[TaskRun] = []
        while (msg := self._next_ready(queues, run_delayed)) is not None:
            if len(runs) >= max_tasks:
                self.broker.published.insert(0, msg)
                raise RuntimeError(
                    f"drain() ran {max_tasks} tasks and the queue is still not "
                    "empty. A task may be re-enqueueing itself; raise max_tasks "
                    "if this is expected."
                )
            runs.append(await self._run(msg))
        return runs

    @overload
    async def call[R](self, task: task_module.Task[None, R]) -> R: ...

    @overload
    async def call[M: BaseModel, R](
        self,
        task: task_module.Task[M, R],
        data: M,
    ) -> R: ...

    async def call(
        self,
        task: task_module.Task[Any, Any],
        data: BaseModel | None = None,
    ) -> Any:
        """
        Run ``task`` now, with the same input you would pass to send().

        Unlike ``await task(...)``, the input goes through a JSON round-trip and
        dependencies (including overrides) are resolved, exactly as on a worker.
        Always raises the task's exception.
        """
        msg = _round_trip(task.build_message(data))
        return await worker.execute(self.app, msg)

    def _next_ready(
        self,
        queues: list[str] | None,
        run_delayed: bool,
    ) -> message.TaskMessage | None:
        now = datetime.now(tz=UTC)
        for i, msg in enumerate(self.broker.published):
            if queues is not None and msg.queue not in queues:
                continue
            if not run_delayed and msg.eta is not None and msg.eta > now:
                continue
            return self.broker.published.pop(i)
        return None

    async def _run(self, msg: message.TaskMessage) -> TaskRun:
        try:
            result = await worker.execute(self.app, _round_trip(msg))
        except Exception as exc:
            run = TaskRun(msg=msg, error=exc)
            self.runs.append(run)
            if self.raise_errors:
                raise
            logger.exception("Task %s[%s] failed: %s", msg.task_name, msg.id, exc)
            return run
        run = TaskRun(msg=msg, result=result)
        self.runs.append(run)
        return run
