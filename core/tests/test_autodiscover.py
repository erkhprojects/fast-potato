from __future__ import annotations

import pytest

from brokers.memory import MemoryBroker
from core import FastPotato


class TestAutodiscover:
    def test_tasks_not_registered_before_autodiscover(self):
        from core.tests._fixtures.shared_app import fixture_app
        # fresh app — nothing imported yet on its own
        app = FastPotato(
            "fixture2",
            broker=MemoryBroker(),
            include=["core.tests._fixtures.orders_tasks"],
        )
        assert len(app._registry) == 0

    def test_autodiscover_registers_tasks_from_module(self):
        from core.tests._fixtures.shared_app import fixture_app
        fixture_app.autodiscover()
        assert any("process_order" in k for k in fixture_app._registry)
        assert any("cancel_order" in k for k in fixture_app._registry)

    def test_autodiscover_registers_tasks_from_multiple_modules(self):
        from core.tests._fixtures.shared_app import fixture_app
        fixture_app.autodiscover()
        assert any("send_welcome" in k for k in fixture_app._registry)

    def test_autodiscover_is_idempotent(self):
        from core.tests._fixtures.shared_app import fixture_app
        fixture_app.autodiscover()
        count_after_first = len(fixture_app._registry)
        fixture_app.autodiscover()
        assert len(fixture_app._registry) == count_after_first

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
            include=["core.tests._fixtures.orders_tasks"],
        )
        assert "core.tests._fixtures.orders_tasks" in app._include
