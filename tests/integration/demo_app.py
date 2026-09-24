from __future__ import annotations

import os
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel

from fast_potato import Depends, FastPotato, Potato
from fast_potato.brokers.rabbitmq import RabbitMQBroker
from fast_potato.brokers.redis import RedisBroker

# Resolve data dump directory
shared_dir_env = os.getenv("SHARED_DIR")
if shared_dir_env:
    DATA_DIR = Path(shared_dir_env)
elif Path("/shared").is_dir():
    DATA_DIR = Path("/shared")
else:
    DATA_DIR = Path(__file__).parent / "testdir4data_dump"


# --- 0. Task Input Model (the only data sent over the broker) ---


class WriteRequest(BaseModel):
    payload: str
    output_filename: str


# --- 1. Potato App-Level Singleton ---


class DeploymentConfig(Potato):
    prefix: str = "DEPLOY_TEST"


# --- 2. One-Layer Sync & Async Function Dependencies ---


def get_sync_salt() -> str:
    return "SYNC_SALT_11"


async def get_async_token() -> str:
    return "ASYNC_TOK_22"


# --- 3. Generator Dependencies with Teardown (Sync & Async) ---


def get_sync_audit_log() -> Generator[str]:
    # Setup
    yield "SYNC_GEN_OK"
    # Teardown


async def get_async_db_pool() -> AsyncGenerator[str]:
    # Setup
    yield "ASYNC_GEN_OK"
    # Teardown


# --- 4. Bare Class Dependency (Inferred from Type) ---


class MetricsTracker:
    def __init__(self) -> None:
        self.metric_name = "METRIC_TRACKER_OK"


# --- 5. Nested Dependencies (Two Layers Deep) ---


def get_base_region() -> str:
    return "REGION_US"


def get_cluster_id(region: Annotated[str, Depends(get_base_region)]) -> str:
    return f"CLUSTER_42_{region}"


class SecurityContext:
    def __init__(
        self,
        cluster: Annotated[str, Depends(get_cluster_id)],
        token: Annotated[str, Depends(get_async_token)],
    ) -> None:
        self.cluster = cluster
        self.token = token

    def summary(self) -> str:
        return f"{self.cluster}:{self.token}"


# --- Redis Application & Task ---

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
broker_redis = RedisBroker(url=redis_url, poll_interval=1.0)
app_redis = FastPotato(
    "deploy_app_redis", broker=broker_redis, potato=DeploymentConfig()
)


@app_redis.task(queue="deploy_redis")
async def process_and_write_redis(
    request: WriteRequest,
    # 1. Potato singleton
    config: Annotated[DeploymentConfig, Depends],
    # 2. One-layer sync function
    sync_salt: Annotated[str, Depends(get_sync_salt)],
    # 3. One-layer async function
    async_tok: Annotated[str, Depends(get_async_token)],
    # 4. Sync generator (yield + teardown)
    sync_gen: Annotated[str, Depends(get_sync_audit_log)],
    # 5. Async generator (yield + teardown)
    async_gen: Annotated[str, Depends(get_async_db_pool)],
    # 6. Bare class dependency (inferred)
    metrics: Annotated[MetricsTracker, Depends()],
    # 7. Nested class dependency (2 layers deep)
    sec: Annotated[SecurityContext, Depends(SecurityContext)],
    # 8. Default-value parameter dependency
    direct_dep: str = Depends(get_sync_salt),
) -> None:
    content = ":".join(
        [
            config.prefix,
            sync_salt,
            async_tok,
            sync_gen,
            async_gen,
            metrics.metric_name,
            sec.summary(),
            direct_dep,
            request.payload,
        ]
    )
    out_p = Path(request.output_filename)
    if out_p.is_absolute() and out_p.parent.exists():
        path = out_p
    else:
        path = DATA_DIR / out_p.name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# --- RabbitMQ Application & Task ---

rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
broker_rmq = RabbitMQBroker(url=rabbitmq_url)
app_rmq = FastPotato("deploy_app_rmq", broker=broker_rmq, potato=DeploymentConfig())


@app_rmq.task(queue="deploy_rmq")
async def process_and_write_rmq(
    request: WriteRequest,
    # 1. Potato singleton
    config: Annotated[DeploymentConfig, Depends],
    # 2. One-layer sync function
    sync_salt: Annotated[str, Depends(get_sync_salt)],
    # 3. One-layer async function
    async_tok: Annotated[str, Depends(get_async_token)],
    # 4. Sync generator (yield + teardown)
    sync_gen: Annotated[str, Depends(get_sync_audit_log)],
    # 5. Async generator (yield + teardown)
    async_gen: Annotated[str, Depends(get_async_db_pool)],
    # 6. Bare class dependency (inferred)
    metrics: Annotated[MetricsTracker, Depends()],
    # 7. Nested class dependency (2 layers deep)
    sec: Annotated[SecurityContext, Depends(SecurityContext)],
    # 8. Default-value parameter dependency
    direct_dep: str = Depends(get_sync_salt),
) -> None:
    content = ":".join(
        [
            config.prefix,
            sync_salt,
            async_tok,
            sync_gen,
            async_gen,
            metrics.metric_name,
            sec.summary(),
            direct_dep,
            request.payload,
        ]
    )
    out_p = Path(request.output_filename)
    if out_p.is_absolute() and out_p.parent.exists():
        path = out_p
    else:
        path = DATA_DIR / out_p.name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
