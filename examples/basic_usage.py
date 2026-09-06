"""
Basic usage example for fast-potato.

Run with:
    poetry run python examples/basic_usage.py
"""

import asyncio
import json
from pydantic import BaseModel
from fast_potato import FastPotato
from fast_potato.brokers import MemoryBroker

broker = MemoryBroker()
app = FastPotato("my_app", broker=broker)


# --- Define your models (nested Pydantic is fully supported) ---

class Address(BaseModel):
    city: str
    country: str


class User(BaseModel):
    name: str
    age: int
    address: Address


# --- Register tasks ---

@app.task
async def add(x: int, y: int) -> int:
    return x + y


@app.task
async def send_welcome_email(user: User) -> None:
    print(f"[task] sending welcome email to {user.name} at {user.address.city}")


# --- Main ---

async def main() -> None:
    # 1. Fire immediately
    msg = await add.send(10, 20)
    print("immediate send:")
    print(json.loads(msg.model_dump_json()), "\n")

    # 2. Fire after a delay of 60 seconds
    msg = await add.send(10, 20, delay=60)
    print("send with delay=60s — eta:", msg.eta, "\n")

    # 3. Send a task with a nested Pydantic model as argument
    user = User(name="Alice", age=30, address=Address(city="Berlin", country="DE"))
    msg = await send_welcome_email.send(user)
    print("send with pydantic arg:")
    print(json.loads(msg.model_dump_json()), "\n")

    # 4. Call the task function directly (no broker, runs in-process)
    result = await add(3, 4)
    print("direct call result:", result, "\n")

    # 5. Consume and execute queued tasks with the Worker
    from fast_potato import Worker
    worker = Worker(app=app)
    print("--- Worker draining queue ---")
    count = await worker.run_until_empty()
    print(f"Worker processed {count} tasks successfully.")


if __name__ == "__main__":
    asyncio.run(main())
