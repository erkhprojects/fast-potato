from brokers.memory import MemoryBroker
from core import FastPotato

fixture_app = FastPotato(
    "fixture",
    broker=MemoryBroker(),
    include=[
        "core.tests._fixtures.orders_tasks",
        "core.tests._fixtures.emails_tasks",
    ],
)
