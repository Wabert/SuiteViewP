from threading import Thread, get_ident
from unittest.mock import Mock

import pytest

from suiteview.core import rates


def test_scope_closes_helper_instances_on_worker_even_after_error(monkeypatch):
    events = []

    class Connection:
        def close(self):
            events.append(("close", get_ident()))

    def connect(*args, **kwargs):
        assert kwargs["timeout"] == 15
        events.append(("connect", get_ident()))
        return Connection()

    monkeypatch.setattr(rates.pyodbc, "connect", connect)
    monkeypatch.setattr(rates, "local_data_enabled", lambda: False)

    def work():
        with pytest.raises(ValueError, match="calculation"):
            with rates.owned_rate_connections():
                first = rates.Rates()
                second = rates.Rates()
                assert first._get_connection().timeout == 30
                second._get_connection()
                raise ValueError("calculation failed")

    thread = Thread(target=work)
    thread.start()
    thread.join()
    assert [kind for kind, _ in events] == ["connect", "connect", "close", "close"]
    assert all(owner == thread.ident for _, owner in events)


def test_worker_scope_does_not_reuse_or_close_global_singleton(monkeypatch):
    global_rates = rates.Rates()
    connection = global_rates._connection = Mock()
    monkeypatch.setattr(rates, "_rates_instance", global_rates)
    with rates.owned_rate_connections():
        scoped = rates.get_rates_instance()
        assert scoped is not global_rates
        assert rates.get_rates_instance() is scoped
    assert rates.get_rates_instance() is global_rates
    connection.close.assert_not_called()


def test_nested_scope_closes_only_its_own_instances():
    with rates.owned_rate_connections():
        outer = rates.Rates()
        outer._connection = outer_connection = Mock()
        with rates.owned_rate_connections():
            inner = rates.Rates()
            inner._connection = inner_connection = Mock()
        inner_connection.close.assert_called_once()
        outer_connection.close.assert_not_called()
    outer_connection.close.assert_called_once()
