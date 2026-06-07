import brokers
import driver

fixture_app = driver.app.FastPotato(
    "fixture",
    broker=brokers.memory.MemoryBroker(),
    include=[
        "driver.tests._fixtures.orders_tasks",
        "driver.tests._fixtures.emails_tasks",
    ],
)
