"""Summary shadow values share the engine basis across UI, exports and snapshots."""

from dataclasses import replace
from datetime import date

from openpyxl import load_workbook
import pytest

from suiteview.illustration.core.summary_results import (
    ALL_COLUMNS, SHADOW_SUMMARY_COLUMNS, SUMMARY_SCHEMA_VERSION,
    json_safe_rows, project_summary_row,
)
from suiteview.illustration.debug.summary_export import build_summary_workbook
from suiteview.illustration.core.regression_runner import compare_rows, RATE_TOLERANCE
from suiteview.illustration.models.calc_state import MonthlyState
from suiteview.illustration.models.policy_data import IllustrationPolicyData


def _state():
    return MonthlyState(
        date=date(2026, 9, 26), policy_year=12, policy_month=11, attained_age=36,
        shadow_target_prem=745.84, shadow_coi=23.45, shadow_epu=4.56,
        shadow_rider_charges=7.89, shadow_md=40.9,
        shadow_int_rate=0.045, shadow_eff_rate=0.0037,
        shadow_bav=800, shadow_av=750, shadow_eav=752.81,
        shadow_eav_less_debt=652.81, rider_charges=2.34,
    )


def test_shadow_summary_preserves_workbook_order_units_and_end_value():
    row = project_summary_row(IllustrationPolicyData(), _state())
    assert SUMMARY_SCHEMA_VERSION == 3
    assert tuple(row) == ALL_COLUMNS
    assert tuple(row)[-7:] == (
        "vShadow_TP", "Shadow COI", "Shadow EPU", "Rider Charges",
        "Shadow MD", "Shadow Int Rate", "vShadowEAV",
    )
    assert [row[column] for column in SHADOW_SUMMARY_COLUMNS] == [
        745.84, 23.45, 4.56, 7.89, 40.9, 0.045, 752.81,
    ]
    assert row["Rider COI"] == 2.34
    encoded = json_safe_rows([row])[0]
    assert encoded["Date"] == "2026-09-26"
    for column in SHADOW_SUMMARY_COLUMNS:
        assert encoded[column] == row[column]


def test_shadow_summary_retains_zero_and_negative_values():
    policy = IllustrationPolicyData()
    zero = project_summary_row(policy, MonthlyState())
    assert [zero[column] for column in SHADOW_SUMMARY_COLUMNS] == [0.0] * 7
    negative = project_summary_row(policy, replace(_state(), shadow_eav=-123.45))
    assert negative["vShadowEAV"] == -123.45


def test_shadow_interest_uses_rate_regression_tolerance():
    expected = json_safe_rows([project_summary_row(IllustrationPolicyData(), _state())])
    actual = [dict(expected[0], **{"Shadow Int Rate": 0.04501})]
    result = compare_rows("case", "Case", "current", actual, expected)
    assert len(result.diffs) == 1
    assert result.diffs[0].field == "Shadow Int Rate"
    assert result.diffs[0].tolerance == RATE_TOLERANCE


@pytest.mark.parametrize("field, column", [
    ("shadow_target_prem", "vShadow_TP"), ("shadow_coi", "Shadow COI"),
    ("shadow_epu", "Shadow EPU"), ("shadow_rider_charges", "Rider Charges"),
    ("shadow_md", "Shadow MD"), ("shadow_int_rate", "Shadow Int Rate"),
    ("shadow_eav", "vShadowEAV"),
])
def test_shadow_summary_rejects_nonfinite_values(field, column):
    with pytest.raises(ValueError, match=column):
        project_summary_row(
            IllustrationPolicyData(), replace(_state(), **{field: float("nan")}),
        )


def test_current_and_guaranteed_workbooks_include_shadow_columns(tmp_path):
    policy = IllustrationPolicyData()
    current = _state()
    guaranteed = replace(current, shadow_eav=700.25, shadow_md=42.5)
    path = tmp_path / "summary.xlsx"
    workbook = build_summary_workbook(policy, [current], [guaranteed])
    try:
        workbook.save(path)
    finally:
        workbook.close()
    saved = load_workbook(path, read_only=True, data_only=True)
    try:
        for sheet, state in zip(saved.worksheets, [current, guaranteed]):
            headers, values = list(sheet.values)
            assert headers == ALL_COLUMNS
            row = dict(zip(headers, values))
            expected = project_summary_row(policy, state)
            for column in SHADOW_SUMMARY_COLUMNS:
                assert row[column] == expected[column]
    finally:
        saved.close()
