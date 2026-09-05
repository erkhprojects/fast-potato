from __future__ import annotations

import pytest

from fast_potato import FastPotato
from fast_potato.brokers import MemoryBroker
from tests._fixtures import shared_app


class TestAutodiscover:
    def test_tasks_not_registered_before_autodiscover(self):
        # fresh app — nothing imported yet on its own
        app = FastPotato(
            "fixture2",
            broker=MemoryBroker(),
            include=["tests._fixtures.orders_tasks"],
        )
        assert len(app._registry) == 0

    def test_autodiscover_registers_tasks_from_module(self):
        shared_app.fixture_app.autodiscover()
        assert any("process_order" in k for k in shared_app.fixture_app._registry)
        assert any("cancel_order" in k for k in shared_app.fixture_app._registry)

    def test_autodiscover_registers_tasks_from_multiple_modules(self):
        shared_app.fixture_app.autodiscover()
        assert any("send_welcome" in k for k in shared_app.fixture_app._registry)

    def test_autodiscover_is_idempotent(self):
        shared_app.fixture_app.autodiscover()
        count_after_first = len(shared_app.fixture_app._registry)
        shared_app.fixture_app.autodiscover()
        assert len(shared_app.fixture_app._registry) == count_after_first

    def test_unknown_module_raises(self):
        app = FastPotato(
            "bad",
            broker=MemoryBroker(),
            include=["myapp.does_not_exist"],
        )
        with pytest.raises(ModuleNotFoundError):
            app.autodiscover()

    def test_empty_include_autodiscover_is_noop(self):
        app = FastPotato("empty", broker=MemoryBroker())
        app.autodiscover()  # should not raise
        assert app._registry == {}

    def test_include_stored_on_app(self):
        app = FastPotato(
            "test",
            broker=MemoryBroker(),
            include=["tests._fixtures.orders_tasks"],
        )
        assert "tests._fixtures.orders_tasks" in app._include
