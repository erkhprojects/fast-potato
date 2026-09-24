"""
Basic usage example for fast-potato.

Demonstrates:
1. Tasks take one pydantic model as their input (nested models are fine).
2. Tasks without input.
3. Sending immediately and with a delay.
4. Custom (non-pydantic) field types via pydantic's own Annotated serializers.
5. Calling the task function directly, and consuming the queue with a Worker.

Run with:
    uv run python examples/basic_usage.py
"""

import asyncio
import json
from typing import Annotated

from pydantic import BaseModel, PlainSerializer, PlainValidator

from fast_potato import FastPotato, Worker
from fast_potato.brokers import MemoryBroker

broker = MemoryBroker()
app = FastPotato("my_app", broker=broker)


# --- Define your input models (nested Pydantic is fully supported) ---


class Address(BaseModel):
    city: str
    country: str


class User(BaseModel):
    name: str
    age: int
    address: Address


class AddInput(BaseModel):
    x: int
    y: int


# --- A custom, non-pydantic type ---
# Serialization is pydantic's job: tell it how to dump and load the type.


class Point:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y

    def __repr__(self) -> str:
        return f"Point({self.x}, {self.y})"


def _parse_point(value: object) -> Point:
    if isinstance(value, Point):
        return value
    if isinstance(value, str):
        x, y = value.split(",")
        return Point(float(x), float(y))
    raise ValueError(f"Cannot parse Point from {value!r}")


PointField = Annotated[
    Point,
    PlainValidator(_parse_point),
    PlainSerializer(lambda p: f"{p.x},{p.y}", return_type=str),
]


class DrawInput(BaseModel):
    start: PointField
    end: PointField


# --- Register tasks ---


@app.task
async def add(numbers: AddInput) -> int:
    return numbers.x + numbers.y


@app.task
async def send_welcome_email(user: User) -> None:
    print(f"[task] sending welcome email to {user.name} at {user.address.city}")


@app.task
async def draw_line(line: DrawInput) -> None:
    print(f"[task] drawing line from {line.start} to {line.end}")


@app.task
async def ping() -> None:
    print("[task] pong")


# --- Main ---


async def main() -> None:
    # 1. Fire immediately. The input model is dumped into msg.payload.
    msg = await add.send(AddInput(x=10, y=20))

    print("immediate send:")
    print(json.loads(msg.model_dump_json()), "\n")

    # 2. Fire after a delay of 60 seconds
    msg = await add.send(AddInput(x=10, y=20), delay=60)
    print("send with delay=60s — eta:", msg.eta, "\n")

    # 3. Send a task whose input is a nested Pydantic model
    user = User(name="Alice", age=30, address=Address(city="Berlin", country="DE"))
    msg = await send_welcome_email.send(user)
    print("send with nested pydantic input:")
    print(json.loads(msg.model_dump_json()), "\n")

    # 4. Custom types travel as whatever their PlainSerializer returns
    msg = await draw_line.send(DrawInput(start=Point(0, 0), end=Point(3, 4)))
    print("send with custom type fields — payload:", msg.payload, "\n")

    # 5. Tasks without input are sent with no data
    msg = await ping.send()
    print("send without input — payload:", msg.payload, "\n")

    # 6. Call the task function directly (no broker, runs in-process)
    result = await add(AddInput(x=3, y=4))
    print("direct call result:", result, "\n")

    # 7. Consume and execute queued tasks with the Worker
    #    (the delayed add() stays queued until its ETA)
    worker = Worker(app=app)
    print("--- Worker processing queued tasks ---")
    worker_task = asyncio.create_task(worker.run())
    await asyncio.sleep(0.05)
    worker.stop()
    await worker_task
    print("Worker finished processing tasks successfully.")


if __name__ == "__main__":
    asyncio.run(main())
