"""Tests for the RegisteredDataSource model + store + ODBC helpers (Phase 4 3b)."""
from __future__ import annotations

import pytest

from suiteview.audit import data_source_store
from suiteview.audit.data_source import (
    KIND_ACCESS,
    KIND_ODBC,
    RegisteredDataSource,
    datasource_kind_label,
)
from suiteview.core import odbc_utils


def test_model_round_trips_and_stamps_id():
    ds = RegisteredDataSource(name="Prod DB2", dsn="NEON_DSN", dialect="DB2",
                              notes="production", tags=["db2"])
    assert ds.id
    restored = RegisteredDataSource.from_dict(ds.to_dict())
    assert restored.id == ds.id
    assert restored.name == "Prod DB2"
    assert restored.dsn == "NEON_DSN"
    assert restored.dialect == "DB2"
    assert restored.notes == "production"
    assert restored.tags == ["db2"]


def test_legacy_dict_without_id_gets_one():
    ds = RegisteredDataSource.from_dict({"name": "X", "dsn": "D"})
    assert ds.id


def test_target_is_dsn_or_path():
    assert RegisteredDataSource(name="a", kind=KIND_ODBC, dsn="D").target == "D"
    assert RegisteredDataSource(name="b", kind=KIND_ACCESS, path="c:/x.accdb").target == "c:/x.accdb"


def test_kind_label():
    assert datasource_kind_label(RegisteredDataSource(name="a", dialect="DB2")) == "DB2"
    assert datasource_kind_label(RegisteredDataSource(name="a")) == "ODBC"
    assert datasource_kind_label(RegisteredDataSource(name="a", kind=KIND_ACCESS)) == "MS Access"


@pytest.fixture
def store_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SUITEVIEW_DATA_SOURCES_DIR", str(tmp_path))
    return tmp_path


def test_store_save_load_and_delete(store_dir):
    ds = RegisteredDataSource(name="Acceptance", dsn="NEON_DSNT", dialect="DB2")
    data_source_store.save_data_source(ds)

    assert [s.id for s in data_source_store.list_data_sources()] == [ds.id]
    loaded = data_source_store.load_data_source_by_id(ds.id)
    assert loaded is not None and loaded.dsn == "NEON_DSNT"

    data_source_store.delete_data_source_by_id(ds.id)
    assert data_source_store.list_data_sources() == []
    assert data_source_store.load_data_source_by_id(ds.id) is None


def test_dsn_is_registered(store_dir):
    assert not data_source_store.dsn_is_registered("NEON_DSN")
    data_source_store.save_data_source(
        RegisteredDataSource(name="Prod", dsn="NEON_DSN", dialect="DB2"))
    assert data_source_store.dsn_is_registered("neon_dsn")  # case-insensitive
    assert not data_source_store.dsn_is_registered("OTHER")


def test_store_rename_leaves_no_stale_file(store_dir):
    ds = RegisteredDataSource(name="Old", dsn="D")
    data_source_store.save_data_source(ds)
    ds.name = "New"
    data_source_store.save_data_source(ds)
    sources = data_source_store.list_data_sources()
    assert len(sources) == 1
    assert sources[0].name == "New"


def test_list_installed_dsns_is_a_list():
    # Smoke test — whatever DSNs (if any) are installed, the shape holds.
    result = odbc_utils.list_installed_dsns()
    assert isinstance(result, list)
    assert all(isinstance(name, str) and isinstance(driver, str)
               for name, driver in result)


def test_probe_bogus_dsn_fails_gracefully():
    ok, message = odbc_utils.probe_dsn_connection("__NOT_A_REAL_DSN__")
    assert ok is False
    assert isinstance(message, str) and message


def test_access_round_trips_with_path(store_dir):
    ds = RegisteredDataSource(name="Claims Archive", kind=KIND_ACCESS,
                              path=r"C:\data\claims.accdb", dialect="ACCESS")
    data_source_store.save_data_source(ds)
    loaded = data_source_store.load_data_source_by_id(ds.id)
    assert loaded is not None
    assert loaded.kind == KIND_ACCESS
    assert loaded.path == r"C:\data\claims.accdb"
    assert loaded.target == r"C:\data\claims.accdb"


def test_access_connection_string_has_driver_and_dbq():
    conn = odbc_utils.access_connection_string(r"C:\data\x.accdb")
    assert "DRIVER={" in conn
    assert "DBQ=C:\\data\\x.accdb" in conn


def test_access_helpers_handle_missing_file_gracefully():
    ok, message = odbc_utils.probe_access_connection(r"C:\nope\missing.accdb")
    assert ok is False
    assert isinstance(message, str) and message
    assert odbc_utils.list_access_tables(r"C:\nope\missing.accdb") == []
