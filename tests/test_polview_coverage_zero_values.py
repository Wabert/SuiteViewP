from decimal import Decimal

import pytest

from suiteview.polview.models.policy_information import PolicyInformation
from suiteview.polview.ui.tabs.coverages_tab import CoveragesTab


def _policy(value, vpu=1000, advanced=True):
    policy = object.__new__(PolicyInformation)
    policy._coverages = None
    policy._benefits = None
    policy._band_cache = {}
    rows = {
        "LH_COV_PHA": [{
            "COV_PHA_NBR": 1,
            "PLN_DES_SER_CD": "1U135D00",
            "COV_UNT_QTY": value,
            "OGN_SPC_UNT_QTY": value,
            "COV_VPU_AMT": vpu,
            "ANN_PRM_UNT_AMT": value,
            "INS_ISS_AGE": 0,
        }],
        "LH_SPM_BNF": [{
            "COV_PHA_NBR": 1,
            "SPM_BNF_TYP_CD": "A",
            "SPM_BNF_SBY_CD": "1",
            "BNF_UNT_QTY": value,
            "BNF_VPU_AMT": vpu,
            "BNF_RT_FCT": value,
            "BNF_ANN_PPU_AMT": value,
            "BNF_ISS_AGE": 0,
            "RNL_RT_IND": "1",
        }],
        "LH_SST_XTR_CRG": [{
            "COV_PHA_NBR": 1,
            "SST_XTR_TYP_CD": "2",
            "XTR_PER_1000_AMT": value,
        }],
    }
    policy.fetch_table = lambda table: rows.get(table, [])
    policy.data_item = lambda table, field, *_args: {
        ("LH_BAS_POL", "NON_TRD_POL_IND"): "1" if advanced else "0",
        ("LH_COV_PHA", "PRD_LIN_TYP_CD"): "U" if advanced else "0",
        ("LH_COV_INS_RNL_RT", "RNL_RT"): value,
    }.get((table, field))
    policy.cov_renewal_index = lambda *_args: 0
    policy.renewal_cov_rateclass = lambda *_args: ""
    policy.benefit_renewal_rate = lambda *_args: (
        Decimal(str(value)) if value is not None and str(value).strip() else None
    )
    return policy


@pytest.mark.parametrize("value", [0, 0.0, Decimal("0.00"), "0", None, "", "  ", 12.5])
@pytest.mark.parametrize("advanced", [True, False])
def test_coverage_and_benefit_numeric_values_preserve_zero(value, advanced):
    policy = _policy(value, advanced=advanced)
    expected = Decimal(str(value)) if value is not None and str(value).strip() else None
    amount = expected * 1000 if expected is not None else None
    coverage, = policy.get_coverages()
    benefit, = policy.get_benefits()

    assert coverage.units == expected
    assert coverage.orig_units == expected
    assert coverage.face_amount == amount
    assert coverage.orig_amount == amount
    assert coverage.premium_rate == expected
    assert coverage.annual_premium_per_unit == expected
    assert coverage.cov_annual_premium == (expected * expected if expected is not None else None)
    assert coverage.flat_extra == expected
    assert benefit.units == expected
    assert benefit.benefit_amount == amount
    assert benefit.rating_factor == expected
    assert benefit.coi_rate == expected


@pytest.mark.parametrize("vpu", [0, Decimal("0"), None, "", 1000])
def test_zero_and_missing_value_per_unit_are_distinct(vpu):
    policy = _policy(2, vpu=vpu)
    expected_vpu = Decimal(str(vpu)) if vpu is not None and vpu != "" else None
    expected_amount = 2 * expected_vpu if expected_vpu is not None else None
    coverage, = policy.get_coverages()
    benefit, = policy.get_benefits()

    assert coverage.vpu == expected_vpu
    assert coverage.face_amount == expected_amount
    assert coverage.orig_amount == expected_amount
    assert benefit.vpu == expected_vpu
    assert benefit.benefit_amount == expected_amount


def _cells(table):
    return {
        table._data_table.horizontalHeaderItem(col).text(): table.item(0, col).text()
        for col in range(table.columnCount())
    }


@pytest.mark.parametrize("value, expected", [(0, "0"), (None, "")])
@pytest.mark.parametrize("advanced", [True, False])
def test_coverages_tab_displays_zero_without_filling_missing_values(qtbot, value, expected, advanced):
    policy = _policy(value, advanced=advanced)
    tab = CoveragesTab()
    qtbot.addWidget(tab)
    tab._populate_coverages_from_policy(policy, policy.get_coverages())
    tab._populate_benefits_from_policy(policy.get_benefits())

    coverage = _cells(tab.cov_table)
    benefit = _cells(tab.bnf_table)
    for field in ("Amount", "Flat", "Rate"):
        assert coverage[field] == expected
    if advanced:
        assert coverage["Orig Amt"] == expected
    else:
        assert "Orig Amt" not in coverage
    for field in ("Units", "Rate", "RenewRate"):
        assert benefit[field] == expected
    assert benefit["Rating"] == ("0%" if value is not None else "")
    assert coverage["IssAge"] == benefit["IssAge"] == "0"
    assert coverage["Tbl"] == coverage["Tbl Cease Date"] == coverage["Flat Cease"] == ""


def test_nonrenewing_benefit_keeps_renewal_rate_not_applicable(qtbot):
    benefit, = _policy(0).get_benefits()
    benefit.renewal_indicator = "0"
    tab = CoveragesTab()
    qtbot.addWidget(tab)
    tab._populate_benefits_from_policy([benefit])
    assert _cells(tab.bnf_table)["RenewRate"] == ""
