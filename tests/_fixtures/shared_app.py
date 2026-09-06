from fast_potato import FastPotato
from fast_potato.brokers import MemoryBroker

fixture_app = FastPotato(
    "fixture",
    broker=MemoryBroker(),
    task_modules=[
        "tests._fixtures.orders_tasks",
        "tests._fixtures.emails_tasks",
    ],
)
