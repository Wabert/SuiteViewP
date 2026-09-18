from datetime import date
from types import SimpleNamespace

import openpyxl
import pytest
from unittest.mock import Mock

from suiteview.core.access_control import AccessDeniedError

from suiteview.abrquote.models.abr_data import (
    ABRPolicyData,
    ABRQuoteResult,
    MedicalAssessment,
)
from suiteview.abrquote.ui.output_panel import OutputPanel


@pytest.mark.parametrize("writable", [False, True])
def test_print_detail_uses_entered_ul_deduction_after_max_partial(tmp_path, monkeypatch, writable):
    filepath = tmp_path / "detail.xlsx"
    panel = SimpleNamespace(
        _policy=ABRPolicyData(
            policy_number="U1234567",
            product_type="UL",
            face_amount=100_000,
            min_face_amount=25_000,
        ),
        _result=ABRQuoteResult(
            partial_eligible_db=75_000,
            premium_before="$125.00",
            premium_after_partial="$0.00",
            quote_date=date(2026, 7, 24),
        ),
        _assessment=MedicalAssessment(),
        _derived_values={},
        _mort_detail=[],
        _apv_detail=[],
        _apv_summary={},
        _get_accel_inputs=lambda: (100_000, 25_000),
        _get_after_partial_deduction=lambda: "42.75",
    )

    guard = Mock(side_effect=None if writable else AccessDeniedError("Support files denied"))
    monkeypatch.setattr(
        "suiteview.abrquote.ui.output_panel.guard_support_files_writable", guard
    )
    if not writable:
        with pytest.raises(AccessDeniedError):
            OutputPanel._write_detail_workbook(panel, str(filepath))
        assert not filepath.exists()
        guard.assert_called_once()
        return

    OutputPanel._write_detail_workbook(panel, str(filepath))
    guard.assert_called_once()

    workbook = openpyxl.load_workbook(filepath, data_only=True)
    assessment = workbook["Assessment"]
    after_partial_row = next(
        row
        for row in assessment.iter_rows()
        if row[0].value == "After (Partial):"
    )
    assert after_partial_row[1].value == "42.75"
    workbook.close()
