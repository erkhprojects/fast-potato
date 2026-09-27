from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

try:
    import aio_pika
    from aio_pika.abc import (
        AbstractChannel,
        AbstractConnection,
        AbstractQueue,
    )
    from aio_pika.connection import make_url
    from aiormq.exceptions import AMQPError
except ImportError as exc:
    raise ImportError(
        "RabbitMQBroker requires the 'rabbitmq' extra: pip install fast-potato[rabbitmq]"
    ) from exc

from fast_potato import message
from fast_potato.brokers import base


class RabbitMQBroker(base.AbstractBroker):
    """
    RabbitMQ broker using aio-pika.

    Supports immediate delivery to persistent queues and delayed task delivery
    via RabbitMQ Dead Letter Exchange (DLX) with message expiration.

    Args:
        url: AMQP connection URL, e.g. "amqp://guest:guest@localhost:5672/"
        connect_timeout: seconds to wait for RabbitMQ before raising
            BrokerConnectionError (default 5)
    """

    def __init__(
        self,
        url: str = "amqp://guest:guest@localhost:5672/",
        connect_timeout: float = base.DEFAULT_CONNECT_TIMEOUT,
    ) -> None:
        self._url = url
        self.connect_timeout = connect_timeout
        self._connection: AbstractConnection | None = None
        self._channel: AbstractChannel | None = None

    @property
    def is_connected(self) -> bool:
        return self._channel is not None and not self._channel.is_closed

    async def connect(self) -> None:
        """Establish a robust AMQP connection and channel."""
        # Build the robust connection ourselves (instead of connect_robust) so we
        # always hold a reference: a failed or timed-out first attempt must be
        # closed, or aio-pika keeps retrying in the background forever.
        connection = aio_pika.RobustConnection(make_url(self._url))
        try:
            async with asyncio.timeout(self.connect_timeout):
                await connection.connect(timeout=self.connect_timeout)
                channel = await connection.channel()
        except (AMQPError, OSError, TimeoutError) as exc:
            await connection.close()
            raise base.BrokerConnectionError.from_exception(
                "RabbitMQ",
                self._url,
                self.connect_timeout,
                exc,
            ) from exc
        self._connection = connection
        self._channel = channel

    async def disconnect(self) -> None:
        """Cleanly close channel and connection."""
        if self._channel is not None and not self._channel.is_closed:
            await self._channel.close()
            self._channel = None
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
            self._connection = None

    def _get_channel(self) -> AbstractChannel:
        if self._channel is None or self._channel.is_closed:
            raise RuntimeError(
                "Broker is not connected. Call connect() or ensure_connected() first."
            )
        return self._channel

    async def publish(self, msg: message.TaskMessage) -> None:
        """
        Publish a task message to the broker.

        If msg.eta is set, route through a dead-letter delay queue with message TTL
        so RabbitMQ automatically routes it to the target queue when the delay elapses.
        """
        channel = self._get_channel()
        payload = msg.model_dump_json().encode("utf-8")

        if msg.eta is None:
            await channel.declare_queue(msg.queue, durable=True)
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=payload,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key=msg.queue,
            )
        else:
            now = datetime.now(tz=UTC)
            delay_seconds = (msg.eta - now).total_seconds()
            if delay_seconds <= 0:
                await channel.declare_queue(msg.queue, durable=True)
                await channel.default_exchange.publish(
                    aio_pika.Message(
                        body=payload,
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    ),
                    routing_key=msg.queue,
                )
            else:
                # Target queue must exist to receive the dead-lettered message
                await channel.declare_queue(msg.queue, durable=True)

                delay_queue_name = f"fast_potato.delayed.{msg.queue}"
                await channel.declare_queue(
                    delay_queue_name,
                    durable=True,
                    arguments={
                        "x-dead-letter-exchange": "",
                        "x-dead-letter-routing-key": msg.queue,
                    },
                )
                await channel.default_exchange.publish(
                    aio_pika.Message(
                        body=payload,
                        expiration=delay_seconds,
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    ),
                    routing_key=delay_queue_name,
                )

    async def consume(self, queues: list[str]) -> AsyncGenerator[message.TaskMessage]:
        """
        Yield TaskMessages continuously from the specified queues.
        """
        channel = self._get_channel()
        incoming: asyncio.Queue[message.TaskMessage] = asyncio.Queue()
        active_subscriptions: list[tuple[AbstractQueue, str]] = []

        async def _on_message(amqp_msg: aio_pika.abc.AbstractIncomingMessage) -> None:
            async with amqp_msg.process(ignore_processed=True):
                task_msg = message.TaskMessage.model_validate_json(
                    amqp_msg.body.decode("utf-8")
                )
                await incoming.put(task_msg)

        for q_name in queues:
            q = await channel.declare_queue(q_name, durable=True)
            tag = await q.consume(_on_message)
            active_subscriptions.append((q, tag))

        try:
            while True:
                task_msg = await incoming.get()
                yield task_msg
        finally:
            for q, tag in active_subscriptions:
                try:
                    await q.cancel(tag)
                except Exception:
                    pass
