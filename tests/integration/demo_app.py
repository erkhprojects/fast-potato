from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from fast_potato import Depends, FastPotato, Potato
from fast_potato.brokers.rabbitmq import RabbitMQBroker
from fast_potato.brokers.redis import RedisBroker


class DeploymentConfig(Potato):
    prefix: str = "DEPLOY_TEST"


def get_auth_token() -> str:
    return "AUTH_SEC_99"


# Redis deployment app
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
broker_redis = RedisBroker(url=redis_url, poll_interval=1.0)
app_redis = FastPotato(
    "deploy_app_redis", broker=broker_redis, potato=DeploymentConfig()
)


@app_redis.task(queue="deploy_redis")
async def process_and_write_redis(
    payload: str,
    output_path: str,
    token: Annotated[str, Depends(get_auth_token)],
    config: Annotated[DeploymentConfig, Depends],
) -> None:
    content = f"{config.prefix}:{token}:{payload}"
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# RabbitMQ deployment app
rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
broker_rmq = RabbitMQBroker(url=rabbitmq_url)
app_rmq = FastPotato("deploy_app_rmq", broker=broker_rmq, potato=DeploymentConfig())


@app_rmq.task(queue="deploy_rmq")
async def process_and_write_rmq(
    payload: str,
    output_path: str,
    token: Annotated[str, Depends(get_auth_token)],
    config: Annotated[DeploymentConfig, Depends],
) -> None:
    content = f"{config.prefix}:{token}:{payload}"
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
