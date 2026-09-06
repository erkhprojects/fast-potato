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
    if shared_path_str:
        p = Path(shared_path_str)
    elif Path("/shared").is_dir():
        p = Path("/shared")
    else:
        p = Path(__file__).parent / "testdir4data_dump"
    p.mkdir(parents=True, exist_ok=True)
    return p


async def test_live_worker_deployment_redis(shared_dir: Path) -> None:
    """
    Test that a deployed worker container running `fast-potato -A demo_app:app_redis`
    consumes a task dispatched over Redis, executes dependency injection, and writes
    the expected output file to the shared directory (mounted to host testdir4data_dump).
    """
    random_str = f"redis_rand_{uuid.uuid4().hex[:10]}"
    filename = f"output_redis_{uuid.uuid4().hex[:8]}.txt"
    output_file = shared_dir / filename

    try:
        await demo_app.broker_redis.connect()
    except Exception as exc:
        pytest.skip(f"Redis is not reachable: {exc}")

    try:
        await demo_app.process_and_write_redis.send(
            payload=random_str, output_filename=filename
        )

        deadline = time.time() + 15.0
        content = ""
        while time.time() < deadline:
            if output_file.exists():
                try:
                    content = output_file.read_text(encoding="utf-8")
                    if content:
                        break
                except Exception:
                    pass
            await asyncio.sleep(0.3)

        if not content:
            raise TimeoutError(
                f"Deployed Redis worker did not create output file {output_file} in time"
            )

        assert (
            content
            == f"DEPLOY_TEST:AUTH_SEC_99_SALT_77:NODE_01_CLUSTER_EU:{random_str}"
        )
    finally:
        await demo_app.broker_redis.disconnect()
        if output_file.exists():
            output_file.unlink()


async def test_live_worker_deployment_rabbitmq(shared_dir: Path) -> None:
    """
    Test that a deployed worker container running `fast-potato -A demo_app:app_rmq`
    consumes a task dispatched over RabbitMQ, executes dependency injection, and writes
    the expected output file to the shared directory (mounted to host testdir4data_dump).
    """
    random_str = f"rmq_rand_{uuid.uuid4().hex[:10]}"
    filename = f"output_rmq_{uuid.uuid4().hex[:8]}.txt"
    output_file = shared_dir / filename

    try:
        await demo_app.broker_rmq.connect()
    except Exception as exc:
        pytest.skip(f"RabbitMQ is not reachable: {exc}")

    try:
        await demo_app.process_and_write_rmq.send(
            payload=random_str, output_filename=filename
        )

        deadline = time.time() + 15.0
        content = ""
        while time.time() < deadline:
            if output_file.exists():
                try:
                    content = output_file.read_text(encoding="utf-8")
                    if content:
                        break
                except Exception:
                    pass
            await asyncio.sleep(0.3)

        if not content:
            raise TimeoutError(
                f"Deployed RabbitMQ worker did not create output file {output_file} in time"
            )

        assert (
            content
            == f"DEPLOY_TEST:AUTH_SEC_99_SALT_77:NODE_01_CLUSTER_EU:{random_str}"
        )
    finally:
        await demo_app.broker_rmq.disconnect()
        if output_file.exists():
            output_file.unlink()
