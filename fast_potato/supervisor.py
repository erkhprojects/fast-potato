from __future__ import annotations

import asyncio
import logging
import multiprocessing as mp
import os
import signal
import sys
import time
from typing import Any

from fast_potato import scheduler, worker

logger = logging.getLogger("fast_potato.supervisor")


class ProcessSupervisor:
    """
    Manages OS worker processes and optional scheduler process using multiprocessing spawn.
    """

    def __init__(
        self,
        app_str: str,
        queues: list[str],
        concurrency: int = 10,
        processes: int = 1,
        log_level: str = "INFO",
    ) -> None:
        self.app_str = app_str
        self.queues = queues
        self.concurrency = concurrency
        self.processes = max(1, processes)
        self.log_level = log_level
        self._ctx = mp.get_context("spawn")
        self._workers: list[Any] = []
        self._stopping = False

    def start(self) -> None:
        """Spawn worker processes (and scheduler if configured) and monitor them."""
        app = worker.import_app(self.app_str)
        app.autodiscover()

        logger.info(
            "Starting supervisor for app '%s': %d worker process(es) on queues %s (concurrency=%d)",
            self.app_str,
            self.processes,
            self.queues,
            self.concurrency,
        )

        # Hook signals in master process
        def _master_sig_handler(signum: int, frame: Any) -> None:
            logger.info("Supervisor received shutdown signal (%s), terminating processes...", signum)
            self.stop()

        signal.signal(signal.SIGINT, _master_sig_handler)
        signal.signal(signal.SIGTERM, _master_sig_handler)

        # 1. Spawn worker processes
        for i in range(self.processes):
            p = self._ctx.Process(
                target=worker.run_worker,
                args=(self.app_str, self.queues, self.concurrency, self.log_level),
                name=f"fast_potato-worker-{i+1}",
            )
            p.start()
            self._workers.append(p)
            logger.info("Spawned worker process %s (PID=%d)", p.name, p.pid)

        # 2. Spawn exactly one scheduler process if schedules are configured
        if app.schedules:
            sched_proc = self._ctx.Process(
                target=scheduler.run_scheduler,
                args=(self.app_str, self.log_level),
                name="fast_potato-scheduler",
            )
            sched_proc.start()
            self._workers.append(sched_proc)
            logger.info(
                "Spawned scheduler process %s (PID=%d) with %d schedule(s)",
                sched_proc.name,
                sched_proc.pid,
                len(app.schedules),
            )

        # Monitor loop
        try:
            while not self._stopping:
                all_dead = True
                for p in self._workers:
                    if p.is_alive():
                        all_dead = False
                        break
                if all_dead:
                    break
                time.sleep(0.5)
        finally:
            self._cleanup()

    def stop(self) -> None:
        """Signal all child worker processes to terminate."""
        self._stopping = True
        for p in self._workers:
            if p.is_alive():
                try:
                    os.kill(p.pid, signal.SIGTERM)
                except OSError:
                    pass

    def _cleanup(self) -> None:
        """Join all child worker processes cleanly."""
        for p in self._workers:
            p.join(timeout=3.0)
            if p.is_alive():
                logger.warning("Worker %s did not terminate in time, sending SIGKILL...", p.name)
                p.kill()
                p.join()
        logger.info("All worker processes shut down.")
