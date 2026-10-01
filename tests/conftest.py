from pathlib import Path

import pytest


# Module-level singletons bound to the profile directory (or a live connection)
# that was active when they were first created. Reset per test so one test's
# profile (database, encryption key, repositories) or cached connection cannot
# leak into the next.
_PROFILE_BOUND_SINGLETONS = (
    ("suiteview.data.database", "_db_instance"),
    ("suiteview.data.repositories", "_connection_repo"),
    ("suiteview.data.repositories", "_metadata_cache_repo"),
    ("suiteview.data.repositories", "_email_repo"),
    ("suiteview.core.credential_manager", "_credential_manager"),
    ("suiteview.core.connection_manager", "_connection_manager"),
    ("suiteview.core.rates", "_rates_instance"),
)


@pytest.fixture(autouse=True)
def _isolated_profile(tmp_path_factory, monkeypatch):
    """Give every test a private SuiteView profile instead of the user's ~/.suiteview.

    Tests that need a specific profile still set SUITEVIEW_PROFILE_DIR
    themselves; that monkeypatch simply overrides this default.
    """
    import importlib

    monkeypatch.setenv("SUITEVIEW_PROFILE_DIR", str(tmp_path_factory.mktemp("profile")))
    monkeypatch.setenv("APPDATA", str(tmp_path_factory.mktemp("appdata")))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path_factory.mktemp("localappdata")))
    for module_name, attribute in _PROFILE_BOUND_SINGLETONS:
        module = importlib.import_module(module_name)
        monkeypatch.setattr(module, attribute, None)
    yield


_LIVE_MARKERS = ("live_db2", "integration", "outlook")
_UL_RATES_RECORDED: dict = {}
_UL_RATES_USED: set = set()


@pytest.fixture(autouse=True)
def _no_live_odbc(request, monkeypatch):
    """Block real ODBC connections in unit tests.

    This machine has live DSNs (UL_Rates, VRD Prod, NEON_DSN, …); a unit test
    that forgets to fake its data access must fail loudly instead of reading
    from — or writing to — a real database. Tests that genuinely need a live
    source carry one of the live markers (deselected by default in pytest.ini).
    Tests that fake connections monkeypatch pyodbc.connect or the
    core.odbc_utils factory themselves, which overrides this guard.

    UL_Rates is the one exception: its queries are answered from a recorded
    replay (tests/ul_rates_replay.py) so rate-dependent tests stay hermetic.
    """
    if any(request.node.get_closest_marker(name) for name in _LIVE_MARKERS):
        yield
        return
    import pyodbc

    from tests import ul_rates_replay

    real_connect = pyodbc.connect
    replay = ul_rates_replay.load_replay()

    def _guarded(connection_string, *args, **kwargs):
        if str(connection_string).strip().upper() == "DSN=UL_RATES":
            if ul_rates_replay.recording_enabled():
                return ul_rates_replay.ReplayConnection(
                    replay, _UL_RATES_RECORDED, real_connect(connection_string, *args, **kwargs))
            return ul_rates_replay.ReplayConnection(replay, used=_UL_RATES_USED)
        raise pyodbc.InterfaceError(
            "IM002",
            f"Live ODBC connection blocked in a unit test ({connection_string!r}); "
            "fake the connection or mark the test live_db2/integration.",
        )

    monkeypatch.setattr(pyodbc, "connect", _guarded)
    yield


def pytest_sessionfinish(session, exitstatus):
    """Persist UL_Rates results captured in record mode, or prune unused ones."""
    from tests import ul_rates_replay

    if ul_rates_replay.recording_enabled() and _UL_RATES_RECORDED:
        ul_rates_replay.save_replay(_UL_RATES_RECORDED)
    elif ul_rates_replay.pruning_enabled():
        if exitstatus != 0:
            print(f"\n{ul_rates_replay.PRUNE_ENV}: session did not pass; replay file left unchanged.")
        else:
            dropped = ul_rates_replay.prune_replay(_UL_RATES_USED)
            print(f"\n{ul_rates_replay.PRUNE_ENV}: dropped {dropped} unused recorded queries.")


_INTEGRATION_MODULES = {
    "test_access_unique.py",
    "test_attachment_manager.py",
    "test_caching.py",
    "test_data_source.py",
    "test_db2_columns.py",
    "test_db2_query_performance.py",
    "test_db2_tables.py",
    "test_dynamic_query.py",
    "test_email_manager.py",
    "test_excel_template.py",
    "test_field_dictionary.py",
    "test_file_source.py",
    "test_file_source_intake.py",
    "test_forge_engine.py",
    "test_forge_runtime.py",
}

_LIVE_DB2_MODULES = {
    "test_db2_columns.py",
    "test_db2_query_performance.py",
    "test_db2_tables.py",
}

_OUTLOOK_MODULES = {
    "test_email_manager.py",
}

_PERFORMANCE_MODULES = {
    "test_db2_query_performance.py",
}

_PERFORMANCE_TESTS = {
    "test_illustration_md_check.py::test_matrix_monthly_deduction_checks_within_cent",
    "test_illustration_solve_premium_to_target.py::test_real_engine_sv_target_equals_av_on_a_chargeless_policy",
    "test_illustration_solve_premium_to_target.py::test_real_engine_av_target_matches_premium_arithmetic",
    "test_illustration_solve_premium_to_target.py::test_real_engine_premium_stops_at_the_row_span",
    "test_illustration_max_level_solve.py::test_real_engine_guideline_drop_lowers_max_level",
}

# Individual tests that read real policies from live DB2 (not just recorded rates).
_LIVE_DB2_TESTS = {
    "test_illustration_md_check.py::test_premium_waiver_rider_basis_checks_within_cent",
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply suite tiers by test module so legacy diagnostics stay isolated."""
    for item in items:
        module_name = Path(str(item.path)).name
        test_id = f"{module_name}::{item.name}"
        if module_name in _INTEGRATION_MODULES:
            item.add_marker(pytest.mark.integration)
        if module_name in _LIVE_DB2_MODULES or test_id in _LIVE_DB2_TESTS:
            item.add_marker(pytest.mark.live_db2)
            item.add_marker(pytest.mark.integration)
        if module_name in _OUTLOOK_MODULES:
            item.add_marker(pytest.mark.outlook)
        if module_name in _PERFORMANCE_MODULES or test_id in _PERFORMANCE_TESTS:
            item.add_marker(pytest.mark.performance)
            item.add_marker(pytest.mark.integration)
