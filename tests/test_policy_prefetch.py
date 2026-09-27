"""Private connection ownership, safe snapshots and render manifest coverage."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Event, get_ident
from types import SimpleNamespace
import re

import pytest
import pyodbc
from PyQt6.QtCore import Qt

from suiteview.polview.services import policy_service
from suiteview.core.db2_connection import DB2Connection
from suiteview.polview.models.policy_data import CachedReadError, _ConnectionManager
from suiteview.polview.services import policy_prefetch as prefetch
from suiteview.polview.services.policy_prefetch import _open_connection
from suiteview.polview.ui.policy_load_controller import _LoadJob, _PolicyWorker


class DriverRow:
    """An ODBC-like row which cannot be deep-copied."""

    def __init__(self, values):
        self.values = tuple(values)

    def __iter__(self):
        return iter(self.values)

    def __getitem__(self, index):
        return self.values[index]

    def __deepcopy__(self, memo):
        raise AssertionError("Driver row crossed the snapshot boundary")


class Connection:
    def __init__(self, tables):
        self.tables = tables
        self.owner = get_ident()
        self.calls = []
        self.closed = None
        self.fail = set()
        self.companies = ["01"]
        self.system = "I"

    def cursor(self):
        assert get_ident() == self.owner
        return Cursor(self)

    def close(self):
        assert get_ident() == self.owner
        self.closed = get_ident()


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.description = None
        self.rows = []

    def setinputsizes(self, sizes):
        pass

    def execute(self, sql, parameters=()):
        conn = self.connection
        conn.calls.append((sql, parameters, get_ident()))
        table = re.search(r"FROM (?:DB2TAB|UNIT|CYBERTEK|CKSR)\.(\w+)", sql).group(1)
        if table == "TH_POL_MVRY_VAL":
            raise RuntimeError("SQLCODE = -204: DB2TAB.TH_POL_MVRY_VAL IS AN UNDEFINED NAME")
        if table in conn.fail:
            raise RuntimeError(f"{table} offline")
        if "SELECT CK_CMP_CD" in sql:
            system, number, *company = parameters
            self.rows = [
                DriverRow((co, number, system, f"{number} TEST"))
                for co in conn.companies
                if (not company or co == company[0]) and system == conn.system
            ]
        elif "SELECT DISTINCT CK_CMP_CD" in sql:
            self.rows = [DriverRow((co,)) for co in conn.companies]
        else:
            rows = conn.tables.get(table, [])
            columns = list(rows[0]) if rows else []
            self.description = [(column,) for column in columns]
            self.rows = [DriverRow(row[c] for c in columns) for row in rows]
        return self

    def fetchall(self):
        return self.rows

    def close(self):
        pass


@pytest.fixture
def source(monkeypatch):
    tables = {
        "LH_BAS_POL": [{
            "NON_TRD_POL_IND": "1", "PRD_LIN_TYP_CD": "U",
            "NXT_MVRY_PRC_DT": date(2026, 10, 15), "PRM_PAY_STA_REA_CD": "01",
            "SVC_AGC_NBR": "", "POL_ISS_ST_CD": "", "NSD_MD_CD": "",
            "PMT_FQY_PER": 1, "POL_PRM_AMT": 0, "SUS_CD": "0",
            "POL_STS_CD": "10",
            "PRM_PAID_TO_DT": None, "LST_ANV_DT": date(2026, 1, 15),
            "PRM_BILL_TO_DT": None, "NXT_BIL_DT": None,
            "NXT_YR_END_PRC_DT": date(2027, 1, 15), "LST_FIN_DT": None,
            "NFO_OPT_TYP_CD": "0", "PRI_DIV_OPT_CD": "0",
            "POL_1035_XCG_IND": "", "LN_PLN_ITS_RT": 0, "BIL_FRM_CD": "0",
            "OGN_ETR_CD": "", "LST_ETR_CD": "", "USR_RES_CD": "",
            "SVC_AGT_NBR": "", "LN_TYP_CD": "",
        }],
        "LH_COV_PHA": [{
            "COV_PHA_NBR": 1, "PLN_DES_SER_CD": "SYNTH",
            "ISSUE_DT": date(2020, 1, 15), "COV_MT_EXP_DT": date(2100, 1, 15),
            "COV_UNT_QTY": 100, "COV_VPU_AMT": 1000, "INS_ISS_AGE": 30,
            "NBR_OF_LIVES_CD": "1", "PRD_LIN_TYP_CD": "U",
            "INS_CLS_CD": "N", "PLN_BSE_SRE_CD": "SYN", "LIF_PLN_SUB_SRE_CD": "TH",
        }],
        "LH_NON_TRD_POL": [{
            "TFDF_CD": "2", "CDR_PCT": 250,
            "IN_GRA_PER_IND": "0", "DTH_BNF_PLN_OPT_CD": "1",
            "POL_GUA_ITS_RT": 0, "GRA_THD_RLE_CD": "", "GRA_PER_EXP_DT": None,
            "PRF_LN_ITS_CRG_RT": 0, "PRF_LN_OPT_CD": "",
        }],
        "LH_POL_MVRY_VAL": [{"MVRY_DT": date(2026, 9, 15), "CSV_AMT": 200}],
    }
    connections = []

    def connect(region):
        conn = Connection(tables)
        connections.append(conn)
        return conn

    monkeypatch.setattr(prefetch, "_open_connection", connect)
    monkeypatch.setattr(
        _ConnectionManager, "get_connection",
        lambda *args: pytest.fail("Touched global connection manager"),
    )
    return SimpleNamespace(tables=tables, connections=connections)


@pytest.mark.parametrize("stage", ["coverages", "targets"])
def test_transport_retry_replaces_private_connection_and_clears_failed_reads(
    source, monkeypatch, stage,
):
    original_execute = Cursor.execute
    failed = []
    target = "SELECT CK_CMP_CD" if stage == "coverages" else "FROM DB2TAB.LH_POL_TARGET"

    def execute(cursor, sql, parameters=()):
        if target in sql and not failed:
            failed.append(cursor.connection)
            raise pyodbc.Error("08001", "[08001] SQLCODE = -30081 TCP/IP COMMUNICATIONS ERROR")
        return original_execute(cursor, sql, parameters)

    monkeypatch.setattr(Cursor, "execute", execute)

    def run():
        worker = _PolicyWorker()
        results = []
        worker.completed.connect(
            lambda *args: results.append(args), Qt.ConnectionType.DirectConnection)
        try:
            worker.execute(_LoadJob(1, "coverages", "TEST", "CKPR", "01", Event()))
            if stage == "targets":
                worker.execute(_LoadJob(1, "targets", "TEST", "CKPR", "01", Event()))
            assert results[-1][3] == ""
            assert results[-1][2].policy.exists
            assert not results[-1][2].policy._data._table_errors
            assert len(source.connections) == 2
            assert failed[0] is source.connections[0]
            assert source.connections[0].closed == get_ident()
            assert source.connections[1].closed is None
        finally:
            worker._close_session()

    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(run).result()


def test_retry_cannot_reacquire_failed_physical_odbc_connection(source, monkeypatch):
    from suiteview.core import local_dev

    physical_connections = []
    original_execute = Cursor.execute

    def connect(*args, **kwargs):
        if pyodbc.pooling and physical_connections:
            return physical_connections[0]
        connection = Connection(source.tables)
        connection.getinfo = lambda _key: "rdvodbc64.dll"
        physical_connections.append(connection)
        return connection

    def execute(cursor, sql, parameters=()):
        if cursor.connection is physical_connections[0]:
            raise pyodbc.Error("08S01", "[DV][ODBC Driver]Host communication failed")
        return original_execute(cursor, sql, parameters)

    monkeypatch.setattr(prefetch, "_open_connection", _open_connection)
    monkeypatch.setattr(local_dev, "local_data_enabled", lambda: False)
    monkeypatch.setattr(pyodbc, "connect", connect)
    monkeypatch.setattr(Cursor, "execute", execute)

    def run():
        worker = _PolicyWorker()
        results = []
        worker.completed.connect(
            lambda *args: results.append(args), Qt.ConnectionType.DirectConnection,
        )
        try:
            worker.execute(_LoadJob(1, "coverages", "TEST", "CKPR", "01", Event()))
            assert results[-1][3] == ""
            assert results[-1][2].policy.exists
            assert len(physical_connections) == 2
            assert physical_connections[0].closed == get_ident()
        finally:
            worker._close_session()

    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(run).result()


def test_worker_owns_connections_and_snapshots_are_plain_independent(source):
    global_cache = dict(policy_service._cache)
    global_connections = dict(DB2Connection._connections)
    session = prefetch.PolicyLoadSession("test")
    with ThreadPoolExecutor(max_workers=1) as worker:
        initial = worker.submit(session.load_initial).result()
        later = worker.submit(session.prepare, "persons").result()
        with pytest.raises(RuntimeError, match="owner thread"):
            session.prepare("activity")
        worker.submit(session.close).result()
    conn = source.connections[0]
    assert len(source.connections) == 1
    assert conn.owner == conn.closed != get_ident()
    assert all(call[2] == conn.owner for call in conn.calls)
    assert policy_service._cache == global_cache
    assert DB2Connection._connections == global_connections
    assert initial.policy._data._conn_mgr is None
    assert initial.policy._rates is None
    assert isinstance(initial.policy._data._table_cache["LH_COV_PHA"]["rows"][0], tuple)
    assert "LH_CTT_CLIENT" not in initial.policy._data._table_cache
    assert "VH_POL_HAS_LOC_CLT" not in initial.policy._data._table_cache
    assert "VH_POL_HAS_LOC_CLT" in later.policy._data._table_cache
    initial.policy.coverages.get_coverages()[0].raw_data["COV_UNT_QTY"] = 999
    assert later.policy.coverages.get_coverages()[0].raw_data["COV_UNT_QTY"] == 100
    assert not {"FH_FIXED", "LH_CSH_VAL_LOAN", "LH_FND_VAL_LOAN",
                "LH_UNAPPLIED_PTP", "LH_TAMRA_7_PY_YR"} & initial.policy._data._table_cache.keys()


def test_failed_fetch_is_not_empty_success_and_retry_clears_error(source):
    session = prefetch.PolicyLoadSession("TEST")
    initial = session.load_initial()
    conn = source.connections[0]
    conn.fail.add("FH_FIXED")
    with pytest.raises(RuntimeError, match="FH_FIXED offline"):
        session.prepare("activity")
    assert "FH_FIXED" not in initial.policy._data._table_cache
    conn.fail.clear()
    result = session.prepare("activity")
    assert result.policy.fetch_table("FH_FIXED") == []
    assert not result.policy._data._table_errors
    session.close()


@pytest.mark.parametrize("rows,expected", [
    ([], None),
    ([{"MVRY_DT": date(2026, 9, 15), "CSV_AMT": None}], None),
    ([{"MVRY_DT": date(2026, 9, 15), "CSV_AMT": 0}], 0),
    ([{"MVRY_DT": date(2026, 9, 15), "CSV_AMT": 125}], 125),
])
def test_missing_monthliversary_value_never_probes_an_invented_table(source, qtbot, rows, expected):
    from suiteview.polview.ui.tabs.coverages_tab import CoveragesTab

    source.tables["LH_POL_MVRY_VAL"] = rows
    source.tables["LH_NON_TRD_POL"][0]["DTH_BNF_PLN_OPT_CD"] = "2"
    session = prefetch.PolicyLoadSession("TEST")
    try:
        prepared = session.load_initial()
        policy = prepared.policy
        widget = CoveragesTab()
        qtbot.addWidget(widget)
        with policy.cached_reads_only():
            assert policy.values.accumulation_value == expected
            assert policy.coverages.current_account_value == expected
            assert policy.values.cash_surrender_value == expected
            assert policy.values.net_amount_at_risk is None
            widget.load_data_from_policy(policy)
        assert not policy._data._table_errors
        assert all("TH_POL_MVRY_VAL" not in sql
                   for sql, _, _ in source.connections[0].calls)
    finally:
        session.close()


def test_net_amount_at_risk_reads_recorded_monthliversary_nar(source):
    source.tables["LH_POL_MVRY_VAL"] = [{
        "MVRY_DT": date(2026, 9, 15), "CSV_AMT": 125, "NAR_AMT": 99875,
    }]
    session = prefetch.PolicyLoadSession("TEST")
    try:
        session.load_initial()
        policy = session.prepare("advprod").policy
        with policy.cached_reads_only():
            assert policy.values.net_amount_at_risk == 99875
            assert policy.values.cash_surrender_value == 125
        assert all("TH_POL_MVRY_VAL" not in sql
                   for sql, _, _ in source.connections[0].calls)
    finally:
        session.close()


@pytest.mark.parametrize("roles,number_of_lives,lives_code,expected", [
    (["00", "01", "10"], "1", "0", "Single"),
    (["00", "10"], "2", "0", "Joint First to Die"),
    (["00", "01"], "3", "0", "Joint Second to Die"),
    (["00", "20"], " 3 ", "2", "Joint Second to Die"),
    (["00", "10"], 1, "3", "Single"),
])
def test_single_joint_uses_number_of_lives_in_both_policy_displays(
    source, qtbot, roles, number_of_lives, lives_code, expected,
):
    from PyQt6.QtWidgets import QApplication
    from suiteview.illustration.ui.policy_tab import IllustrationPolicyTab
    from suiteview.polview.ui.tabs.coverages_tab import CoveragesTab

    source.tables["LH_CTT_CLIENT"] = [
        {"PRS_CD": role, "PRS_SEQ_NBR": 1, "BIR_DT": None} for role in roles
    ]
    source.tables["LH_COV_PHA"][0]["LIVES_COV_CD"] = lives_code
    source.tables["LH_COV_PHA"][0]["NBR_OF_LIVES_CD"] = number_of_lives
    session = prefetch.PolicyLoadSession("TEST")
    try:
        policy = session.load_initial().policy
        tab = CoveragesTab()
        qtbot.addWidget(tab)
        calls_before_render = len(source.connections[0].calls)
        with policy.cached_reads_only():
            assert policy.coverages.number_of_lives_code == str(number_of_lives).strip()
            assert policy.coverages.is_joint_insured == (expected != "Single")
            tab.load_data_from_policy(policy)
        assert tab.joint_label.text() == expected
        assert "LH_CTT_CLIENT" not in policy._data._table_cache
        assert len(source.connections[0].calls) == calls_before_render

        rerun = IllustrationPolicyTab()
        qtbot.addWidget(rerun)
        with session._scope():
            rerun._coverages = policy.coverages.get_coverages()
            rerun._populate_policy_info(policy, {})
        assert rerun.policy_info.get_value("joint_label") == expected
        for widget, label in (
            (tab, tab.joint_label),
            (rerun, rerun.policy_info.joint_label),
        ):
            widget.resize(1160, 700)
            widget.show()
            qtbot.wait(1)
            if QApplication.platformName() == "windows":
                assert label.fontMetrics().horizontalAdvance(expected) <= label.contentsRect().width()
    finally:
        session.close()


@pytest.mark.parametrize("code", [None, "", " ", "0", "4", "X"])
def test_missing_or_invalid_number_of_lives_is_not_assumed_single(source, code):
    source.tables["LH_COV_PHA"][0]["NBR_OF_LIVES_CD"] = code
    session = prefetch.PolicyLoadSession("TEST")
    try:
        with pytest.raises(ValueError, match="NBR_OF_LIVES_CD"):
            session.load_initial()
        with session._scope():
            with pytest.raises(ValueError, match="NBR_OF_LIVES_CD"):
                _ = session._policy.coverages.is_joint_insured
    finally:
        session.close()


def test_number_of_lives_uses_phase_one_not_first_row_or_riders(source):
    base = source.tables["LH_COV_PHA"][0]
    base["NBR_OF_LIVES_CD"] = "3"
    source.tables["LH_COV_PHA"].insert(
        0, {**base, "COV_PHA_NBR": 2, "NBR_OF_LIVES_CD": "1"},
    )
    session = prefetch.PolicyLoadSession("TEST")
    try:
        policy = session.load_initial().policy
        with policy.cached_reads_only():
            assert policy.coverages.number_of_lives_code == "3"
            assert policy.coverages.is_joint_insured
            assert policy.coverages.insured_lives_description == "Joint Second to Die"
    finally:
        session.close()


def test_missing_base_lives_code_does_not_use_a_rider(source):
    source.tables["LH_COV_PHA"][0]["COV_PHA_NBR"] = 2
    session = prefetch.PolicyLoadSession("TEST")
    try:
        with pytest.raises(ValueError, match="NBR_OF_LIVES_CD.*base coverage phase 1"):
            session.load_initial()
    finally:
        session.close()


def test_joint_insured_lookup_failure_is_not_rendered_as_single(source):
    session = prefetch.PolicyLoadSession("TEST")
    try:
        session.load_initial()
        source.connections[0].fail.add("LH_COV_PHA")
        session._policy._data._table_cache.pop("LH_COV_PHA")
        with pytest.raises(RuntimeError, match="LH_COV_PHA offline"):
            session.prepare("coverages")
    finally:
        session.close()


def test_guard_raises_when_loader_swallows_missing_or_failed_table(source):
    session = prefetch.PolicyLoadSession("TEST")
    policy = session.load_initial().policy
    with pytest.raises(CachedReadError, match="FH_FIXED"):
        with policy.cached_reads_only():
            try:
                policy.fetch_table("FH_FIXED")
            except Exception:
                pass
    policy._data._table_cache["FH_FIXED"] = {"columns": [], "rows": []}
    policy._data._table_errors["FH_FIXED"] = "driver failed"
    with pytest.raises(CachedReadError, match="driver failed"):
        with policy.cached_reads_only():
            try:
                policy.fetch_table("FH_FIXED")
            except Exception:
                pass
    with pytest.raises(CachedReadError, match="Rates"):
        with policy.cached_reads_only():
            policy.rates._get_rates()
    session.close()


def test_merge_keeps_identity_and_rejects_cross_policy(source):
    session = prefetch.PolicyLoadSession("TEST")
    gui = session.load_initial().policy
    incoming = session.prepare("persons").policy
    gui.merge_prefetched(incoming)
    assert gui is not incoming
    assert gui.loan_records._policy is gui
    assert "LH_CTT_CLIENT" in gui._data._table_cache
    for field, value in (
        ("_company_code", "04"), ("_region", "CKMO"),
        ("_system_code", "P"), ("_policy_number", "OTHER"),
    ):
        bad = incoming.detached_copy()
        setattr(bad._data, field, value)
        with pytest.raises(ValueError, match="different"):
            gui.merge_prefetched(bad)
    incoming._data._table_cache["LH_CTT_CLIENT"]["columns"].append("NEW")
    assert gui._data._table_cache["LH_CTT_CLIENT"]["columns"] == []
    session.close()


def test_connection_failure_does_not_fall_back_to_pending(source, monkeypatch):
    calls = []

    def fail(region):
        calls.append(region)
        raise RuntimeError("Connection failed")

    monkeypatch.setattr(prefetch, "_open_connection", fail)
    session = prefetch.PolicyLoadSession("TEST")
    with pytest.raises(RuntimeError, match="Connection failed"):
        session.load_initial()
    assert calls == ["CKPR"]
    session.close()


@pytest.mark.parametrize("companies,system", [(["01", "04"], "I"), (["01"], "P"), ([], "I")])
def test_company_chooser_pending_and_not_found(source, monkeypatch, companies, system):
    connection = Connection(source.tables)
    connection.companies = companies
    connection.system = system
    monkeypatch.setattr(prefetch, "_open_connection", lambda region: connection)
    session = prefetch.PolicyLoadSession("TEST")
    result = session.load_initial()
    if len(companies) > 1:
        assert result.policy.identity.available_companies == companies
        assert not result.policy.identity.exists
        assert len(connection.calls) == 1
    elif companies:
        assert result.policy.identity.exists
        assert result.policy.identity.system_code == "P"
    else:
        assert not result.policy.identity.exists
        assert "not found" in result.policy.identity.last_error
    session.close()


def test_gui_registration_never_adds_blank_company_alias(source):
    session = prefetch.PolicyLoadSession("TEST")
    policy = session.load_initial().policy
    private = {("TEST", None, "I", "CKPR"): object()}
    with policy_service.policy_cache_scope(private):
        policy_service.cache_policy_info(policy)
    assert list(private) == [("TEST", "01", "I", "CKPR")]
    session.close()


def test_seed_is_detached_and_does_not_resolve_again(source, monkeypatch):
    first = prefetch.PolicyLoadSession("TEST")
    seed = first.load_initial().policy
    first.close()
    global_cache = dict(policy_service._cache)
    monkeypatch.setattr(
        policy_service, "get_policy_info",
        lambda *args, **kwargs: pytest.fail("Resolved seed performed a policy lookup"),
    )
    second = prefetch.PolicyLoadSession("TEST", seed=seed)
    result = second.load_initial()
    assert len(source.connections) == 1
    assert result.policy is not seed
    assert second._policy is not seed
    assert second._policy._data._conn_mgr is None
    assert second._policy._rates is None
    assert second._cache == {("TEST", "01", "I", "CKPR"): second._policy}
    second.prepare("activity")
    assert len(source.connections) == 2
    assert "FH_FIXED" not in seed._data._table_cache
    assert policy_service._cache == global_cache
    second.close()
    with pytest.raises(ValueError, match="same resolved"):
        prefetch.PolicyLoadSession("OTHER", seed=seed)


@pytest.mark.parametrize("mismatch", [
    {"region": "CKMO"}, {"company_code": "04"}, {"system_code": "P"},
])
def test_seed_rejects_explicit_identity_mismatch(source, mismatch):
    original = prefetch.PolicyLoadSession("TEST")
    seed = original.load_initial().policy
    original.close()
    with pytest.raises(ValueError, match="same resolved"):
        prefetch.PolicyLoadSession("TEST", seed=seed, **mismatch)


def test_pending_seed_preserves_system_and_catches_swallowed_render_reads(source):
    original = prefetch.PolicyLoadSession("TEST")
    seed = original.load_initial().policy
    original.close()
    seed._data._system_code = "P"
    session = prefetch.PolicyLoadSession(
        "test", "ckpr", "01", seed=seed, system_code="p",
    )
    result = session.load_initial()
    assert result.policy.identity.system_code == "P"
    assert ("TEST", "01", "P", "CKPR") in session._cache
    assert ("TEST", "01", "I", "CKPR") not in session._cache
    assert len(source.connections) == 1
    with pytest.raises(CachedReadError, match="FH_FIXED"):
        with result.policy.cached_reads_only():
            try:
                result.policy.fetch_table("FH_FIXED")
            except Exception:
                pass
    assert len(source.connections) == 1
    session.close()


def test_explicit_system_without_seed_does_not_fallback(source):
    session = prefetch.PolicyLoadSession("TEST", system_code="P")
    result = session.load_initial()
    assert not result.policy.identity.exists
    connection = source.connections[0]
    assert len(connection.calls) == 1
    assert connection.calls[0][1][0] == "P"
    session.close()


def test_swallowed_dependency_error_still_fails_initial_and_retries(source, monkeypatch):
    from suiteview.polview.models.policy_sections.coverages import CoveragesSection

    connection = Connection(source.tables)
    connection.fail.add("TH_SST_XTR_CRG")
    monkeypatch.setattr(prefetch, "_open_connection", lambda region: connection)
    original = CoveragesSection.get_coverages

    def swallow(self):
        try:
            self.fetch_table("TH_SST_XTR_CRG")
        except Exception:
            pass
        return original(self)

    monkeypatch.setattr(CoveragesSection, "get_coverages", swallow)
    session = prefetch.PolicyLoadSession("TEST")
    with pytest.raises(RuntimeError, match="TH_SST_XTR_CRG offline"):
        session.load_initial()
    connection.fail.clear()
    result = session.load_initial()
    assert result.policy.coverages.get_coverages()
    assert not result.policy._data._table_errors
    session.close()


def test_reinsurance_is_detached_explicit_and_retries(source, monkeypatch, qtbot):
    from suiteview.core import reinsurance
    from suiteview.polview.models.reinsurance_information import ReinsuranceInformation
    from suiteview.polview.ui.tabs.reinsurance_tab import ReinsuranceTab

    result = reinsurance.TAICessionResult(error="TAI unavailable")
    monkeypatch.setattr(reinsurance, "fetch_tai_cession", lambda number: result)
    global_cache = dict(ReinsuranceInformation._tai_cache)
    session = prefetch.PolicyLoadSession("TEST")
    session.load_initial()
    with pytest.raises(RuntimeError, match="TAI unavailable"):
        session.prepare("reinsurance")
    result.error = ""
    result.month_end = "202608"
    prepared = session.prepare("reinsurance")
    assert isinstance(prepared.payload, ReinsuranceInformation)
    assert prepared.payload.companies == ("01",)
    assert prepared.payload.tai_cession is not result
    assert ReinsuranceInformation._tai_cache == global_cache
    widget = ReinsuranceTab()
    qtbot.addWidget(widget)
    with prepared.policy.cached_reads_only():
        widget.load_data_from_policy(prepared.policy, prepared.payload)
    session.close()


def test_surrender_uses_scoped_policy_and_canonical_engine(source, monkeypatch):
    from suiteview import illustration
    from suiteview.illustration import api as illustration_api
    from suiteview.illustration.core import rate_loader
    from suiteview.illustration.models import plancode_config

    session = prefetch.PolicyLoadSession("TEST")
    session.load_initial()
    segment = SimpleNamespace(coverage_phase=1)
    basis = SimpleNamespace(plancode="SYNTH", base_segment=segment, segments=[segment])
    rates = SimpleNamespace(segment_scr={1: [0, 1]}, scr=[0, 1])
    observed = []

    def build(number, region="CKPR", company_code=None, **kwargs):
        assert policy_service.get_policy_info(number, region, company_code) is session._policy
        observed.append("build")
        return basis

    class Engine:
        def project(
            self, loaded, months=None, future_inputs=None, timing=None,
            stop_on_lapse=True, options=None, bonus_override=None,
            rates_override=None,
        ):
            assert loaded is basis and months == 0 and rates_override is rates
            observed.append("project")
            return [SimpleNamespace(surrender_charge=100, surrender_value=75)]

    monkeypatch.setattr(illustration_api, "build_illustration_data", build)
    monkeypatch.setattr(illustration, "IllustrationEngine", Engine)
    monkeypatch.setattr(plancode_config, "load_plancode", lambda code: object())
    monkeypatch.setattr(rate_loader, "load_rates", lambda *args: rates)
    prepared = session.prepare("advprod")
    assert prepared.payload == prefetch.SurrenderValues(100, 75)
    assert observed == ["build", "project"]
    rates.segment_scr[1] = []
    unavailable = session.prepare("advprod")
    assert isinstance(unavailable.payload, prefetch.SurrenderValuesUnavailable)
    assert "Missing surrender rates" in unavailable.payload.reason
    assert unavailable.policy.values.mv_av(0) == 200
    assert observed == ["build", "project", "build"]
    session.close()


def test_missing_illustration_plan_keeps_advanced_policy_values_available(source, monkeypatch, qtbot):
    from suiteview.illustration import api as illustration_api
    from suiteview.illustration.models import plancode_config
    from suiteview.polview.ui.tabs.adv_prod_tab import AdvProdValuesTab

    monkeypatch.setattr(plancode_config, "_TABLE_CACHE", {})
    monkeypatch.setattr(plancode_config, "_CONFIG_CACHE", {})
    monkeypatch.setattr(
        illustration_api, "build_illustration_data",
        lambda *args: pytest.fail("Unsupported plan must not run illustration calculations"),
    )
    session = prefetch.PolicyLoadSession("TEST")
    session.load_initial()
    try:
        prepared = session.prepare("advprod")
        assert prepared.available
        assert isinstance(prepared.payload, prefetch.SurrenderValuesUnavailable)
        assert "SYNTH" in prepared.payload.reason
        tab = AdvProdValuesTab()
        qtbot.addWidget(tab)
        with prepared.policy.cached_reads_only():
            tab.load_data_from_policy(prepared.policy, prepared.payload)
        assert tab.policy_info._fields["total_av"].text() == "200.00"
        for field in ("surrender_charge", "surrender_value"):
            assert tab.policy_info._fields[field].text() == "N/A"
            assert "no illustration configuration" in tab.policy_info._fields[field].toolTip()
        assert not tab.surrender_notice.isHidden()
        assert tab.mv_values.table._data_table.rowCount() == 1

        with prepared.policy.cached_reads_only():
            tab.load_data_from_policy(prepared.policy, prefetch.SurrenderValues(0, 200))
        assert tab.policy_info._fields["surrender_charge"].text() == "0.00"
        assert tab.policy_info._fields["surrender_value"].text() == "200.00"
        assert tab.surrender_notice.isHidden()
        assert tab.policy_info._fields["surrender_value"].toolTip() == ""
    finally:
        session.close()


@pytest.mark.parametrize("error", [
    KeyError("SA_Basis"), ValueError("invalid rate"), OSError("offline"),
    prefetch.pyodbc.Error("08001", "Rate database unavailable"),
    RuntimeError("Surrender calculation returned no inforce values"),
])
@pytest.mark.parametrize("step", ["configuration", "basis", "rates", "projection"])
def test_optional_surrender_failures_do_not_block_policy_records(
    source, monkeypatch, qtbot, caplog, error, step,
):
    from suiteview import illustration
    from suiteview.illustration import api as illustration_api
    from suiteview.illustration.core import rate_loader
    from suiteview.illustration.models import plancode_config
    from suiteview.polview.ui.tabs.adv_prod_tab import AdvProdValuesTab

    def fail(*args, **kwargs):
        raise error

    segment = SimpleNamespace(coverage_phase=1)
    basis = SimpleNamespace(plancode="SYNTH", base_segment=segment, segments=[segment])
    monkeypatch.setattr(plancode_config, "load_plancode", lambda code: object())
    monkeypatch.setattr(illustration_api, "build_illustration_data", lambda *args, **kwargs: basis)
    monkeypatch.setattr(
        rate_loader, "load_rates",
        lambda *args: SimpleNamespace(segment_scr={1: [0, 1]}, scr=[0, 1]),
    )
    target, attribute = {
        "configuration": (plancode_config, "load_plancode"),
        "basis": (illustration_api, "build_illustration_data"),
        "rates": (rate_loader, "load_rates"),
        "projection": (illustration.IllustrationEngine, "project"),
    }[step]
    monkeypatch.setattr(target, attribute, fail)
    session = prefetch.PolicyLoadSession("TEST")
    session.load_initial()
    try:
        prepared = session.prepare("advprod")
        assert prepared.available
        assert isinstance(prepared.payload, prefetch.SurrenderValuesUnavailable)
        assert str(error) in prepared.payload.reason
        assert str(error) in caplog.text
        tab = AdvProdValuesTab()
        qtbot.addWidget(tab)
        with prepared.policy.cached_reads_only():
            tab.load_data_from_policy(prepared.policy, prepared.payload)
        assert tab.policy_info._fields["total_av"].text() == "200.00"
        assert tab.mv_values.table._data_table.rowCount() == 1
        assert not tab.surrender_notice.isHidden()
        for field in ("surrender_charge", "surrender_value"):
            assert tab.policy_info._fields[field].text() == "N/A"
            assert str(error) in tab.policy_info._fields[field].toolTip()
    finally:
        session.close()


def test_illustration_only_table_failure_does_not_poison_record_snapshot(source, monkeypatch, qtbot):
    from suiteview.illustration import api as illustration_api
    from suiteview.illustration.models import plancode_config
    from suiteview.polview.ui.tabs.adv_prod_tab import AdvProdValuesTab

    session = prefetch.PolicyLoadSession("TEST")
    session.load_initial()
    source.connections[0].fail.add("LH_TAMRA_7_PY_YR")
    monkeypatch.setattr(plancode_config, "load_plancode", lambda code: object())

    def build(*args, **kwargs):
        session._policy.fetch_table("LH_TAMRA_7_PY_YR")

    monkeypatch.setattr(illustration_api, "build_illustration_data", build)
    try:
        prepared = session.prepare("advprod")
        assert isinstance(prepared.payload, prefetch.SurrenderValuesUnavailable)
        assert "LH_TAMRA_7_PY_YR offline" in prepared.payload.reason
        assert not prepared.policy._data._table_errors
        tab = AdvProdValuesTab()
        qtbot.addWidget(tab)
        with prepared.policy.cached_reads_only():
            tab.load_data_from_policy(prepared.policy, prepared.payload)
        assert tab.policy_info._fields["total_av"].text() == "200.00"
        assert tab.mv_values.table._data_table.rowCount() == 1
        assert session.prepare("persons").available
        with pytest.raises(RuntimeError, match="LH_TAMRA_7_PY_YR offline"):
            session.prepare("targets")
    finally:
        session.close()


def test_required_advanced_policy_record_failure_remains_explicit(source, monkeypatch):
    session = prefetch.PolicyLoadSession("TEST")
    session.load_initial()
    session._policy._data.invalidate_table("LH_POL_MVRY_VAL")
    source.connections[0].fail.add("LH_POL_MVRY_VAL")
    monkeypatch.setattr(
        session, "_surrender_values",
        lambda: pytest.fail("Record failure must be detected before optional calculation"),
    )
    try:
        with pytest.raises(RuntimeError, match="LH_POL_MVRY_VAL offline"):
            session.prepare("advprod")
    finally:
        session.close()


def test_worker_rates_are_closed_before_snapshot_handoff(source):
    session = prefetch.PolicyLoadSession("TEST")
    session.load_initial()
    closed = []
    session._policy._rates = SimpleNamespace(close=lambda: closed.append(get_ident()))
    result = session.prepare("persons")
    assert closed == [get_ident()]
    assert result.policy._rates is None
    assert session._policy._rates is None
    session.close()


def test_reinsurance_closes_query_handles_on_failure(monkeypatch):
    from suiteview.core import reinsurance

    closed = []

    class BrokenCursor:
        def execute(self, *args):
            raise RuntimeError("TAI query failed")

        def close(self):
            closed.append("cursor")

    connection = SimpleNamespace(
        cursor=BrokenCursor, close=lambda: closed.append("connection"),
    )
    monkeypatch.setattr(reinsurance, "_get_connection", lambda: connection)
    result = reinsurance.fetch_tai_cession("TEST")
    assert result.error == "TAI query failed"
    assert closed == ["cursor", "connection"]


@pytest.mark.parametrize("annuity_rider", [False, True])
def test_support_prefetch_only_eligibility_and_applicable_annuity(source, monkeypatch, qtbot, annuity_rider):
    from suiteview.polview.services import glp_exception
    from suiteview.polview.ui.tabs.annuity_rider_tab import AnnuityRiderTab

    if annuity_rider:
        source.tables["LH_COV_PHA"].append({
            **source.tables["LH_COV_PHA"][0],
            "COV_PHA_NBR": 2, "PLN_DES_SER_CD": "0699830R",
        })
    monkeypatch.setattr(
        glp_exception, "check_forecast_availability",
        lambda *args: pytest.fail("Support preparation invoked a forecast action"),
    )
    session = prefetch.PolicyLoadSession("TEST")
    initial = session.load_initial()
    assert "FH_FIXED" not in initial.policy._data._table_cache
    result = session.prepare("support")
    assert result.available
    assert result.payload is None
    assert ("FH_FIXED" in result.policy._data._table_cache) is annuity_rider
    with result.policy.cached_reads_only():
        glp_exception.is_glp_exception_eligible(result.policy)
        assert result.policy.coverages.has_annuity_rider is annuity_rider
        if annuity_rider:
            widget = AnnuityRiderTab()
            qtbot.addWidget(widget)
            widget.load_data_from_policy(result.policy)
    session.close()


def test_retry_clears_all_failed_tables_not_just_requested_stage(source):
    session = prefetch.PolicyLoadSession("TEST")
    session.load_initial()
    for table in ("FH_FIXED", "LH_CTT_CLIENT", "LH_POL_TARGET"):
        session._policy._data._table_cache[table] = {"columns": [], "rows": []}
        session._policy._data._table_errors[table] = "old failed read"
    result = session.prepare("persons")
    assert not result.policy._data._table_errors
    assert "FH_FIXED" not in result.policy._data._table_cache
    assert "LH_POL_TARGET" not in result.policy._data._table_cache
    assert result.policy.fetch_table("LH_CTT_CLIENT") == []
    session.close()


@pytest.mark.parametrize("kind", ["policy", "reinsurance"])
def test_private_connections_bound_login_and_query_timeouts(monkeypatch, kind):
    import pyodbc
    from suiteview.core import local_dev, reinsurance

    calls = []
    connection = SimpleNamespace(
        timeout=0, cursor=lambda: SimpleNamespace(close=lambda: None),
        getinfo=lambda key: "other-db2-driver.dll",
    )

    def connect(*args, **kwargs):
        calls.append((args, kwargs))
        return connection

    monkeypatch.setattr(pyodbc, "connect", connect)
    monkeypatch.setattr(local_dev, "local_data_enabled", lambda: False)
    if kind == "policy":
        assert prefetch._open_connection("CKPR") is connection
    else:
        assert reinsurance._get_connection() is connection
    assert calls[0][1]["timeout"] == 15
    assert calls[0][1]["autocommit"] is True
    assert connection.timeout == 30


@pytest.mark.parametrize("state,message,recover", [
    ("HYC00", "SQLSetStmtAttr(SQL_ATTR_QUERY_TIMEOUT)", True),
    ("HYC00", "Some other unsupported feature", False),
    ("08001", "Connection failed", False),
])
def test_timeout_probe_only_recovers_unsupported_query_timeout(
    monkeypatch, caplog, state, message, recover,
):
    import pyodbc
    from unittest.mock import Mock
    from suiteview.core import local_dev

    connection = Mock()
    connection.getinfo.return_value = "other-db2-driver.dll"
    connection.cursor.side_effect = [pyodbc.Error(state, message), Mock()]
    monkeypatch.setattr(pyodbc, "connect", Mock(return_value=connection))
    monkeypatch.setattr(local_dev, "local_data_enabled", lambda: False)
    if recover:
        assert prefetch._open_connection("CKPR") is connection
        assert connection.timeout == 0
        assert "does not support query timeouts" in caplog.text
        connection.close.assert_not_called()
    else:
        with pytest.raises(pyodbc.Error):
            prefetch._open_connection("CKPR")
        connection.close.assert_called_once()


@pytest.mark.parametrize("driver", ["rdvodbc64.dll", r"C:\ODBC\RDVODBC64.DLL"])
def test_dv_driver_never_probes_unsupported_timeout(monkeypatch, caplog, driver):
    from unittest.mock import Mock
    from suiteview.core import local_dev

    connection = Mock(timeout=0)
    connection.getinfo.return_value = driver
    connection.cursor.side_effect = SystemError(
        "<class 'pyodbc.Error'> returned a result with an exception set"
    )
    connect = Mock(return_value=connection)
    monkeypatch.setattr(pyodbc, "connect", connect)
    monkeypatch.setattr(local_dev, "local_data_enabled", lambda: False)
    assert prefetch._open_connection("CKPR") is connection
    connection.getinfo.assert_called_once_with(pyodbc.SQL_DRIVER_NAME)
    connection.cursor.assert_not_called()
    connection.close.assert_not_called()
    assert connection.timeout == 0
    assert connect.call_args.kwargs["timeout"] == 15
    assert "skipping unsupported query timeout" in caplog.text


def test_driver_identification_failure_closes_connection_and_propagates(monkeypatch):
    from unittest.mock import Mock
    from suiteview.core import local_dev

    connection = Mock()
    connection.getinfo.side_effect = pyodbc.Error("08001", "Connection failed")
    monkeypatch.setattr(pyodbc, "connect", Mock(return_value=connection))
    monkeypatch.setattr(local_dev, "local_data_enabled", lambda: False)
    with pytest.raises(pyodbc.Error, match="Connection failed"):
        prefetch._open_connection("CKPR")
    connection.close.assert_called_once()
    connection.cursor.assert_not_called()


@pytest.mark.parametrize("advanced", [False, True])
@pytest.mark.parametrize("stage", [
    "coverages", "policy", "targets", "persons", "activity", "dividends", "loans", "advprod",
])
def test_stage_manifest_renders_without_database_reads(source, monkeypatch, qtbot, stage, advanced):
    from suiteview.polview.ui.tabs.coverages_tab import CoveragesTab
    from suiteview.polview.ui.tabs.policy_tab import PolicyTab
    from suiteview.polview.ui.tabs.targets_tab import TargetsAccumulatorsTab
    from suiteview.polview.ui.tabs.persons_tab import PersonsTab
    from suiteview.polview.ui.tabs.activity_tab import ActivityTab
    from suiteview.polview.ui.tabs.dividends_tab import DividendsTab
    from suiteview.polview.ui.tabs.loans_tab import LoansTab
    from suiteview.polview.ui.tabs.adv_prod_tab import AdvProdValuesTab

    classes = dict(zip(
        ("coverages", "policy", "targets", "persons", "activity", "dividends", "loans", "advprod"),
        (CoveragesTab, PolicyTab, TargetsAccumulatorsTab, PersonsTab, ActivityTab,
         DividendsTab, LoansTab, AdvProdValuesTab),
    ))
    source.tables["LH_BAS_POL"][0]["NON_TRD_POL_IND"] = "1" if advanced else "0"
    monkeypatch.setattr(
        prefetch.PolicyLoadSession, "_surrender_values",
        lambda self: prefetch.SurrenderValues(10, 190),
    )
    session = prefetch.PolicyLoadSession("TEST")
    initial = session.load_initial()
    result = initial if stage == "coverages" else session.prepare(stage)
    count = len(source.connections[0].calls)
    widget = classes[stage]()
    qtbot.addWidget(widget)
    with result.policy.cached_reads_only():
        if stage == "advprod":
            widget.load_data_from_policy(result.policy, result.payload)
        else:
            widget.load_data_from_policy(result.policy)
    assert len(source.connections[0].calls) == count
    session.close()


@pytest.mark.parametrize("stage,table", [
    ("dividends", "LH_PTP_ON_DEP"), ("loans", "LH_CSH_VAL_LOAN"),
])
def test_optional_data_availability_is_row_count_not_nonzero_amount(source, stage, table):
    session = prefetch.PolicyLoadSession("TEST")
    session.load_initial()
    assert not session.prepare(stage).available
    source.tables[table] = [{"LN_PRI_AMT": 0}]
    session._policy._data.invalidate_table(table)
    assert session.prepare(stage).available
    session.close()
