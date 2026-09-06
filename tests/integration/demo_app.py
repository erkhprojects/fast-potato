from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

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
    output_filename: str,
    token: Annotated[str, Depends(get_auth_token)],
    config: Annotated[DeploymentConfig, Depends],
) -> None:
    content = f"{config.prefix}:{token}:{payload}"
    out_p = Path(output_filename)
    if out_p.is_absolute() and out_p.parent.exists():
        path = out_p
    else:
        path = DATA_DIR / out_p.name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# RabbitMQ deployment app
rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
broker_rmq = RabbitMQBroker(url=rabbitmq_url)
app_rmq = FastPotato("deploy_app_rmq", broker=broker_rmq, potato=DeploymentConfig())


@app_rmq.task(queue="deploy_rmq")
async def process_and_write_rmq(
    payload: str,
    output_filename: str,
    token: Annotated[str, Depends(get_auth_token)],
    config: Annotated[DeploymentConfig, Depends],
) -> None:
    content = f"{config.prefix}:{token}:{payload}"
    out_p = Path(output_filename)
    if out_p.is_absolute() and out_p.parent.exists():
        path = out_p
    else:
        path = DATA_DIR / out_p.name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
