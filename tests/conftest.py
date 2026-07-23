from pathlib import Path

import pytest


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


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply suite tiers by test module so legacy diagnostics stay isolated."""
    for item in items:
        module_name = Path(str(item.path)).name
        if module_name in _INTEGRATION_MODULES:
            item.add_marker(pytest.mark.integration)
        if module_name in _LIVE_DB2_MODULES:
            item.add_marker(pytest.mark.live_db2)
        if module_name in _OUTLOOK_MODULES:
            item.add_marker(pytest.mark.outlook)
        test_id = f"{module_name}::{item.name}"
        if module_name in _PERFORMANCE_MODULES or test_id in _PERFORMANCE_TESTS:
            item.add_marker(pytest.mark.performance)
            item.add_marker(pytest.mark.integration)
