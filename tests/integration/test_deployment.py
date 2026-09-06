from __future__ import annotations

import asyncio
import os
import time
import uuid
from pathlib import Path

import pytest

from tests.integration import demo_app


@pytest.fixture
def shared_dir() -> Path:
    shared_path_str = os.getenv("SHARED_DIR")
    if not shared_path_str:
        pytest.skip(
            "SHARED_DIR environment variable is not set; skipping live deployment test."
        )
    p = Path(shared_path_str)
    if not p.is_dir():
        pytest.skip(
            f"SHARED_DIR '{shared_path_str}' does not exist; skipping live deployment test."
        )
    return p


async def test_live_worker_deployment_redis(shared_dir: Path) -> None:
    """
    Test that a deployed worker container running `fast-potato -A demo_app:app_redis`
    consumes a task dispatched over Redis, executes dependency injection, and writes
    the expected output file to the shared Docker volume.
    """
    random_str = f"redis_rand_{uuid.uuid4().hex[:10]}"
    output_file = shared_dir / f"output_redis_{uuid.uuid4().hex[:8]}.txt"

    await demo_app.broker_redis.connect()
    try:
        await demo_app.process_and_write_redis.send(
            payload=random_str, output_path=str(output_file)
        )

        deadline = time.time() + 12.0
        while not output_file.exists():
            if time.time() > deadline:
                raise TimeoutError(
                    f"Deployed Redis worker did not create output file {output_file} in time"
                )
            await asyncio.sleep(0.3)

        content = output_file.read_text(encoding="utf-8")
        assert content == f"DEPLOY_TEST:AUTH_SEC_99:{random_str}"
    finally:
        await demo_app.broker_redis.disconnect()
        if output_file.exists():
            output_file.unlink()


async def test_live_worker_deployment_rabbitmq(shared_dir: Path) -> None:
    """
    Test that a deployed worker container running `fast-potato -A demo_app:app_rmq`
    consumes a task dispatched over RabbitMQ, executes dependency injection, and writes
    the expected output file to the shared Docker volume.
    """
    random_str = f"rmq_rand_{uuid.uuid4().hex[:10]}"
    output_file = shared_dir / f"output_rmq_{uuid.uuid4().hex[:8]}.txt"

    await demo_app.broker_rmq.connect()
    try:
        await demo_app.process_and_write_rmq.send(
            payload=random_str, output_path=str(output_file)
        )

        deadline = time.time() + 12.0
        while not output_file.exists():
            if time.time() > deadline:
                raise TimeoutError(
                    f"Deployed RabbitMQ worker did not create output file {output_file} in time"
                )
            await asyncio.sleep(0.3)

        content = output_file.read_text(encoding="utf-8")
        assert content == f"DEPLOY_TEST:AUTH_SEC_99:{random_str}"
    finally:
        await demo_app.broker_rmq.disconnect()
        if output_file.exists():
            output_file.unlink()
