from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

try:
    from redis.asyncio import Redis
except ImportError as exc:
    raise ImportError(
        "RedisBroker requires the 'redis' extra: pip install fast-potato[redis]"
    ) from exc

from fast_potato import message
from fast_potato.brokers import base

# Redis key used for the delayed-task sorted set (score = unix timestamp)
_DELAYED_KEY = "fast_potato:delayed"


class RedisBroker(base.AbstractBroker):
    """
    Redis broker using LIST queues (LPUSH / BRPOP) for immediate tasks
    and a ZSET for delayed tasks (eta-based scheduling).

    Args:
        url: Redis connection URL, e.g. "redis://localhost:6379/0"
        poll_interval: seconds between delayed-task promotion checks (default 1)
    """

    def __init__(
        self, url: str = "redis://localhost:6379/0", poll_interval: float = 1.0
    ) -> None:
        self._url = url
        self._poll_interval = poll_interval
        self._client: Redis | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        self._client = await Redis.from_url(self._url, decode_responses=True)
        await self._client.ping()

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _redis(self) -> Redis:
        if self._client is None:
            raise RuntimeError(
                "Broker is not connected. Use 'async with broker:' or call connect()."
            )
        return self._client

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    async def publish(self, msg: message.TaskMessage) -> None:
        payload = msg.model_dump_json()

        if msg.eta is None:
            # immediate: push to the queue list (LPUSH; workers BRPOP from right)
            await self._redis.lpush(msg.queue, payload)
        else:
            # delayed: store in a sorted set scored by unix timestamp
            score = msg.eta.timestamp()
            await self._redis.zadd(_DELAYED_KEY, {payload: score})

    # ------------------------------------------------------------------
    # Consume
    # ------------------------------------------------------------------

    async def consume(self, queues: list[str]) -> AsyncGenerator[message.TaskMessage]:
        """
        Yield messages from the given queues.
        Runs a background loop that promotes due delayed tasks before each BRPOP.
        """
        async for msg in self._consume_loop(queues):
            yield msg

    async def _consume_loop(
        self, queues: list[str]
    ) -> AsyncGenerator[message.TaskMessage]:
        while True:
            await self._promote_delayed(queues)

            result = await self._redis.brpop(
                queues, timeout=max(1, int(self._poll_interval))
            )
            if result is None:
                continue

            _, payload = result
            yield message.TaskMessage.model_validate_json(payload)

    async def _promote_delayed(self, active_queues: list[str]) -> None:
        """Move any delayed tasks whose eta has passed into their target queue."""
        now = datetime.now(tz=UTC).timestamp()
        due = await self._redis.zrangebyscore(_DELAYED_KEY, "-inf", now)

        for raw_payload in due:
            payload = (
                raw_payload.decode("utf-8")
                if isinstance(raw_payload, bytes)
                else str(raw_payload)
            )
            msg = message.TaskMessage.model_validate_json(payload)
            if msg.queue in active_queues:
                pipe = self._redis.pipeline()
                pipe.lpush(msg.queue, payload)
                pipe.zrem(_DELAYED_KEY, payload)
                await pipe.execute()
