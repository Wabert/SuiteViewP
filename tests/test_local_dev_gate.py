import pytest

from suiteview.core import db2_connection, local_dev, rates


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        ("", False),
        ("true", False),
        ("yes", False),
        ("on", False),
        ("dev", False),
        ("local", False),
        ("1", True),
    ],
)
def test_local_data_enabled_requires_exact_one(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv(local_dev.LOCAL_DATA_ENV, raising=False)
    else:
        monkeypatch.setenv(local_dev.LOCAL_DATA_ENV, value)

    assert local_dev.local_data_enabled() is expected


def test_direct_local_policy_connection_is_blocked_when_disabled(monkeypatch):
    monkeypatch.delenv(local_dev.LOCAL_DATA_ENV, raising=False)
    monkeypatch.setattr(
        local_dev.sqlite3,
        "connect",
        lambda *_args, **_kwargs: pytest.fail("sqlite3.connect should not be called"),
    )

    with pytest.raises(RuntimeError, match="SUITEVIEW_LOCAL_DATA=1"):
        local_dev.connect_local_policy_database()


def test_direct_local_rates_connection_is_blocked_when_disabled(monkeypatch):
    monkeypatch.delenv(local_dev.LOCAL_DATA_ENV, raising=False)
    monkeypatch.setattr(
        local_dev.sqlite3,
        "connect",
        lambda *_args, **_kwargs: pytest.fail("sqlite3.connect should not be called"),
    )

    with pytest.raises(RuntimeError, match="SUITEVIEW_LOCAL_DATA=1"):
        local_dev.connect_local_rates_database()


def test_db2_connection_does_not_use_local_policy_database_for_truthy_text(monkeypatch):
    fake_connection = object()
    db2_connection.DB2Connection.close_all()
    monkeypatch.setenv(local_dev.LOCAL_DATA_ENV, "true")
    monkeypatch.setattr(
        db2_connection,
        "connect_local_policy_database",
        lambda *_args, **_kwargs: pytest.fail("local policy database should not be used"),
    )
    monkeypatch.setattr(
        db2_connection.pyodbc,
        "connect",
        lambda *_args, **_kwargs: fake_connection,
    )

    assert db2_connection.DB2Connection("CKPR").connect() is fake_connection
    db2_connection.DB2Connection.close_all()


def test_rates_connection_does_not_use_local_rates_database_for_truthy_text(monkeypatch):
    fake_connection = object()
    monkeypatch.setenv(local_dev.LOCAL_DATA_ENV, "yes")
    monkeypatch.setattr(
        rates,
        "connect_local_rates_database",
        lambda *_args, **_kwargs: pytest.fail("local rates database should not be used"),
    )
    monkeypatch.setattr(
        rates.pyodbc,
        "connect",
        lambda *_args, **_kwargs: fake_connection,
    )

    assert rates.Rates()._get_connection() is fake_connection